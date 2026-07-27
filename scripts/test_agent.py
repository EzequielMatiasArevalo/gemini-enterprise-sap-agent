import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

import yaml
import vertexai
from vertexai import agent_engines

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_AGENT_MODULE = "sap_abap_agent_v2"
_SAP_ENV_KEYS = ("SAP_URL", "SAP_USERNAME", "SAP_PASSWORD", "SAP_CLIENT", "SAP_LANGUAGE")


def _agent_config_path(agent_module: str, config_path: Optional[Path]) -> Path:
    if config_path is not None:
        return config_path
    return _REPO_ROOT / agent_module / "config.yaml"


def load_deploy_env_vars(
    agent_module: str = _DEFAULT_AGENT_MODULE,
    config_path: Optional[Path] = None,
) -> Dict[str, str]:
    """Read ``deploy.env_vars`` from ``<agent_module>/config.yaml``."""
    path = _agent_config_path(agent_module, config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Agent config not found: {path}")
    with path.open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle) or {}
    deploy = cfg.get("deploy") or {}
    env_vars = deploy.get("env_vars") or {}
    if not isinstance(env_vars, dict):
        raise ValueError(f"deploy.env_vars must be a mapping in {path}")
    return {str(key): str(value) for key, value in env_vars.items()}


def bootstrap_local_sap_env(
    *,
    agent_module: str = _DEFAULT_AGENT_MODULE,
    config_path: Optional[Path] = None,
    sap_env_source: str = "config",
) -> None:
    """
    Load SAP_* for local verify.

    Priority (shell exports always win if already set):
      - config: deploy.env_vars from config.yaml, then optional .env for gaps
      - env: .env only
      - config-only: config.yaml only
    """
    from dotenv import load_dotenv

    agent_env = _REPO_ROOT / agent_module / ".env"
    config_file = _agent_config_path(agent_module, config_path)

    if sap_env_source in ("config", "config-only"):
        cfg_vars = load_deploy_env_vars(agent_module, config_path)
        for key in _SAP_ENV_KEYS:
            value = cfg_vars.get(key)
            if value and key not in os.environ:
                os.environ[key] = value

    if sap_env_source == "env":
        load_dotenv(agent_env, override=False)
    elif sap_env_source == "config":
        load_dotenv(agent_env, override=False)

    print(f"Config:   {config_file} (exists={config_file.is_file()})")
    print(f"Env file: {agent_env} (exists={agent_env.is_file()})")
    print(f"SAP env source: {sap_env_source}")
    for key in _SAP_ENV_KEYS:
        if key in os.environ:
            display = os.environ[key]
            if key == "SAP_PASSWORD":
                display = "***"
            print(f"  {key}={display}")
        else:
            print(f"  {key}=<not set>")


def run_local_sap_verify(
    *,
    verbose: bool = True,
    agent_module: str = _DEFAULT_AGENT_MODULE,
    config_path: Optional[Path] = None,
    sap_env_source: str = "config",
) -> int:
    """Direct ADT probe using SAP_* from config.yaml (same as deploy) or .env."""
    bootstrap_local_sap_env(
        agent_module=agent_module,
        config_path=config_path,
        sap_env_source=sap_env_source,
    )
    from sap_abap_agent_v2.tools import verify_sap_connection

    print("\n" + "=" * 20 + " SAP local verify " + "=" * 20 + "\n")
    try:
        message = verify_sap_connection(force=True, verbose=verbose)
        print(f"\nResult: {message}\n")
        return 0
    except Exception as exc:
        print(f"\nResult: SAP connection failed — {exc}\n", file=sys.stderr)
        return 1


def parse_args():
    parser = argparse.ArgumentParser(description="Test a deployed Vertex AI Agent Engine")
    parser.add_argument(
        "--ae-resource",
        default=None,
        help="Agent Engine resource name (or set AGENT_ENGINE_RESOURCE)",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("PROJECT_ID"),
        help="GCP project ID",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
        help="GCP region",
    )
    parser.add_argument(
        "--message",
        default=(
            "Llama a la herramienta check_sap_connection (sin argumentos) para "
            "validar la conexión SAP ADT y resume el resultado."
        ),
        help="Message sent to the agent",
    )
    parser.add_argument(
        "--sap-smoke",
        action="store_true",
        help=(
            "Use search_object with query 'SAP' instead of check_sap_connection "
            "(works on older deployments; still triggers SAP connection logs)."
        ),
    )
    parser.add_argument(
        "--agent-module",
        default=_DEFAULT_AGENT_MODULE,
        help="Agent package for config.yaml (default: sap_abap_agent_v2).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (default: <agent_module>/config.yaml).",
    )
    parser.add_argument(
        "--sap-env-source",
        choices=("config", "env", "config-only"),
        default="config",
        help=(
            "SAP_* for local verify: config=deploy.env_vars in config.yaml "
            "(then .env for missing keys); env=.env only; config-only=yaml only."
        ),
    )
    parser.add_argument(
        "--verify-sap",
        action="store_true",
        help=(
            "Run verify_sap_connection locally (SAP_* from config.yaml by default) "
            "with verbose logs before the remote Agent Engine query."
        ),
    )
    parser.add_argument(
        "--verify-sap-only",
        action="store_true",
        help="Only run local verify_sap_connection; skip Agent Engine.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.verify_sap or args.verify_sap_only:
        config_path = Path(args.config) if args.config else None
        code = run_local_sap_verify(
            verbose=True,
            agent_module=args.agent_module,
            config_path=config_path,
            sap_env_source=args.sap_env_source,
        )
        if args.verify_sap_only:
            raise SystemExit(code)
        if code != 0:
            raise SystemExit(code)

    resource = args.ae_resource or os.environ.get("AGENT_ENGINE_RESOURCE")

    if not resource:
        print("=" * 20, " ERROR ", "=" * 20)
        print("AGENT_ENGINE_RESOURCE is not set.")
        print("Set it with:")
        print('  export AGENT_ENGINE_RESOURCE="projects/.../reasoningEngines/..."')
        print("or pass --ae-resource.")
        print()
        if args.project:
            vertexai.init(project=args.project, location=args.region)
        print("Available agents:")
        print("-" * 20)
        for agent in agent_engines.list():
            print(f"Resource Name: {agent.resource_name}")
            print(f"Display Name:  {agent.display_name}")
            print("-" * 20)
        raise SystemExit(1)

    if args.project:
        vertexai.init(project=args.project, location=args.region)

    remote_agent = agent_engines.get(resource)

    print(
        "=================== Remote Agent ============================\n"
        f"    Name: {remote_agent.display_name}\n"
        f"    Resource Name: {remote_agent.resource_name}\n"
        f"    Created/updated at: {remote_agent.update_time}\n"
    )
    if args.sap_smoke:
        message = (
            "Usa search_object con query 'SAP' y maxResults 1 para probar ADT."
        )
    else:
        message = args.message
    print(f"Query: {message}\n")
    if "check_sap_connection" in message and not args.sap_smoke:
        print(
            "Nota: si el agente dice que no tiene check_sap_connection, redeploy "
            "con el código actual:\n"
            f"  uv run python scripts/deploy_agent_engine.py \\\n"
            f"    --project {args.project or '<PROJECT>'} \\\n"
            f"    --update {resource}\n"
        )
    print("--- Stream ---")

    for event in remote_agent.stream_query(
        user_id="test-user",
        message=message,
    ):
        if isinstance(event, dict):
            print(json.dumps(event, indent=2, default=str))
        else:
            print(event)


if __name__ == "__main__":
    main()
