"""Deploy an ADK Agent to Vertex AI Agent Engine.

This script deploys an ADK agent with direct Python function tools
(not MCP subprocess) for Agent Engine compatibility.

The agent module is configurable via ``--agent-module``. The script
reads per-agent deployment settings (requirements, resource limits,
display name, extra packages, env vars, root agent attribute name)
from ``<agent_module>/config.yaml`` under the ``deploy:`` key.

Resolution order for every deploy setting:
    1. Explicit CLI argument (highest priority)
    2. ``deploy.<setting>`` in ``<agent_module>/config.yaml``
    3. Built-in fallback

Infrastructure values (project, region, service account, network
attachment, secret name) still come from CLI args / env vars.

Usage:
    # Create new Agent Engine (default agent: sap_abap_agent_v2)
    python scripts/deploy_agent_engine.py --project <PROJECT_ID>

    # Deploy a different agent module (its own config.yaml drives requirements etc.)
    python scripts/deploy_agent_engine.py \\
        --project <PROJECT_ID> \\
        --agent-module my_other_agent

    # Update existing Agent Engine
    python scripts/deploy_agent_engine.py --project <PROJECT_ID> --update <RESOURCE_NAME>
"""

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import vertexai
import yaml
from vertexai import agent_engines
from google.cloud import secretmanager
from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deploy an ADK agent to Vertex AI Agent Engine",
    )

    # --- Infrastructure / environment-specific flags ---
    parser.add_argument(
        "--project",
        required=True,
        help="GCP project ID",
    )
    parser.add_argument(
        "--region",
        default="us-central1",
        help="GCP region (default: us-central1)",
    )
    parser.add_argument(
        "--staging-bucket",
        default=None,
        help="GCS staging bucket (default: gs://<PROJECT_ID>_cloudbuild)",
    )
    parser.add_argument(
        "--service-account",
        default=None,
        help=(
            "Service account for the Agent Engine "
            "(default: agent-engine-sa@{PROJECT_ID}.iam.gserviceaccount.com)"
        ),
    )
    parser.add_argument(
        "--network-attachment",
        default=None,
        help=(
            "PSC network attachment for the Agent Engine "
            "(default: projects/<PROJECT_ID>/regions/<REGION>/networkAttachments/agent-engine-attachment)"
        ),
    )
    parser.add_argument(
        "--sap-credentials",
        default=None,
        help="SAP credentials Secret Manager name or full version path (default: sap-credentials)",
    )
    parser.add_argument(
        "--update",
        metavar="RESOURCE_NAME",
        help=(
            "Update an existing Agent Engine resource instead of creating a new one. "
            "Pass the full resource name "
            "(e.g. projects/123/locations/us-central1/reasoningEngines/456)"
        ),
    )

    # --- Agent-package selection ---
    parser.add_argument(
        "--agent-module",
        default="sap_abap_agent_v2",
        help=(
            "Python module path of the agent package to deploy. The package "
            "must expose an ``agent`` submodule and a ``config.yaml`` file. "
            "(default: sap_abap_agent_v2)"
        ),
    )
    parser.add_argument(
        "--config",
        default=None,
        help=(
            "Path to the agent config.yaml. "
            "(default: <agent_module>/config.yaml)"
        ),
    )

    # --- Per-deploy overrides (default to values from config.yaml) ---
    parser.add_argument(
        "--agent-attr",
        default=None,
        help=(
            "Override deploy.agent_attr from config.yaml "
            "(attribute name of the root agent inside <agent_module>.agent)."
        ),
    )
    parser.add_argument(
        "--display-name",
        default=None,
        help="Override deploy.display_name from config.yaml.",
    )
    parser.add_argument(
        "--resource-limits",
        default=None,
        help=(
            "Override deploy.resource_limits from config.yaml. "
            "JSON object, e.g. '{\"cpu\":\"4\",\"memory\":\"8Gi\"}'."
        ),
    )
    parser.add_argument(
        "--requirements",
        default=None,
        help=(
            "Override deploy.requirements from config.yaml. JSON array "
            'or comma-separated list, e.g. \'["google-adk>=1.27.0"]\'.'
        ),
    )
    parser.add_argument(
        "--extra-packages",
        default=None,
        help=(
            "Override deploy.extra_packages from config.yaml. "
            "Comma-separated list of local package paths."
        ),
    )
    parser.add_argument(
        "--env-vars",
        default=None,
        help=(
            "Extra non-secret env vars (KEY=value,KEY=value). Merged on top "
            "of deploy.env_vars from config.yaml."
        ),
    )

    return parser.parse_args()


def load_config(agent_module: str, config_path: Optional[str]) -> Dict[str, Any]:
    """Load ``<agent_module>/config.yaml`` (or a custom path)."""
    path = Path(config_path) if config_path else Path(agent_module) / "config.yaml"
    if not path.exists():
        raise SystemExit(
            f"Config file not found: {path}. "
            f"Provide one or pass --config <path>."
        )
    with path.open("r") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise SystemExit(f"Config file {path} must contain a YAML mapping at the top level.")
    return cfg


def load_agent(agent_module: str, agent_attr: str) -> Any:
    """Dynamically import ``<agent_module>.agent`` and return ``agent_attr``."""
    module_path = f"{agent_module}.agent"
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise SystemExit(
            f"Failed to import agent module '{module_path}': {exc}. "
            f"Make sure the package '{agent_module}' is installed or on "
            f"PYTHONPATH and exposes an 'agent' submodule."
        ) from exc

    try:
        return getattr(mod, agent_attr)
    except AttributeError as exc:
        raise SystemExit(
            f"Module '{module_path}' has no attribute '{agent_attr}'. "
            f"Set deploy.agent_attr in config.yaml or pass --agent-attr."
        ) from exc


def _parse_requirements_override(raw: str) -> List[str]:
    """Accept a JSON array or comma-separated list of pip specifiers."""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except json.JSONDecodeError:
        pass
    return [r.strip() for r in raw.split(",") if r.strip()]


def _parse_env_vars(raw: str) -> Dict[str, str]:
    """Accept KEY=value,KEY=value."""
    out: Dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise SystemExit(f"Invalid env var '{pair}': expected KEY=value")
        key, value = pair.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def resolve_deploy_settings(
    args: argparse.Namespace, cfg: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge CLI overrides on top of ``cfg['deploy']`` values."""
    deploy_cfg = cfg.get("deploy", {}) or {}
    if not isinstance(deploy_cfg, dict):
        raise SystemExit("'deploy' section in config.yaml must be a mapping.")

    # Agent attribute name
    agent_attr = args.agent_attr or deploy_cfg.get("agent_attr") or "root_agent"

    # Display name
    display_name = (
        args.display_name
        or deploy_cfg.get("display_name")
        or cfg.get("agent_display_name")
        or "Agent"
    )

    # Resource limits
    if args.resource_limits:
        resource_limits = json.loads(args.resource_limits)
    else:
        resource_limits = deploy_cfg.get("resource_limits") or {"cpu": "8", "memory": "16Gi"}
    if not isinstance(resource_limits, dict):
        raise SystemExit("resource_limits must be a mapping (cpu/memory).")

    # Requirements
    if args.requirements:
        requirements = _parse_requirements_override(args.requirements)
    else:
        requirements = list(deploy_cfg.get("requirements") or [])
    if not requirements:
        raise SystemExit(
            "No requirements provided. Define deploy.requirements in "
            "config.yaml or pass --requirements."
        )

    # Extra packages (default: ./<agent_module>)
    if args.extra_packages:
        extra_packages = [p.strip() for p in args.extra_packages.split(",") if p.strip()]
    else:
        extra_packages = list(deploy_cfg.get("extra_packages") or [f"./{args.agent_module}"])

    # Env vars (config.yaml + CLI; CLI overrides duplicates)
    env_vars: Dict[str, str] = {}
    cfg_env = deploy_cfg.get("env_vars") or {}
    if not isinstance(cfg_env, dict):
        raise SystemExit("deploy.env_vars must be a mapping in config.yaml.")
    for k, v in cfg_env.items():
        env_vars[str(k)] = str(v)
    if args.env_vars:
        env_vars.update(_parse_env_vars(args.env_vars))

    return {
        "agent_attr": agent_attr,
        "display_name": display_name,
        "resource_limits": resource_limits,
        "requirements": requirements,
        "extra_packages": extra_packages,
        "env_vars": env_vars,
    }


def main() -> None:
    args = parse_args()

    PROJECT_ID = os.getenv("PROJECT_ID") or args.project
    LOCATION = os.getenv("REGION") or args.region
    STAGING_BUCKET = (
        os.getenv("STAGING_BUCKET")
        or args.staging_bucket
        or f"gs://{PROJECT_ID}_cloudbuild"
    )

    os.environ["PROJECT_ID"] = PROJECT_ID
    #os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID

    # env_path = Path("sap_agent/.env")
    # if env_path.exists():
    #     print(f"Loading environment variables from {env_path}")
    #     load_dotenv(dotenv_path=env_path)
    # else:
    #     print(f"Note: {env_path} not found. Using Secret Manager for credentials.")

    SERVICE_ACCOUNT = (
        args.service_account or f"agent-engine-sa@{PROJECT_ID}.iam.gserviceaccount.com"
    )
    NETWORK_ATTACHMENT = args.network_attachment or (
        f"projects/{PROJECT_ID}/regions/{LOCATION}"
        f"/networkAttachments/agent-engine-attachment"
    )

    cfg = load_config(args.agent_module, args.config)
    settings = resolve_deploy_settings(args, cfg)

    root_agent = load_agent(args.agent_module, settings["agent_attr"])

    print("Initializing Vertex AI SDK...")
    print(f"  Project:            {PROJECT_ID}")
    print(f"  Location:           {LOCATION}")
    print(f"  Staging Bucket:     {STAGING_BUCKET}")
    print(f"  Network Attachment: {NETWORK_ATTACHMENT}")
    print(f"  Service Account:    {SERVICE_ACCOUNT}")
    print(f"  Agent Module:       {args.agent_module}.{settings['agent_attr']}")
    print(f"  Display Name:       {settings['display_name']}")
    print(f"  Resource Limits:    {settings['resource_limits']}")
    print(f"  Extra Packages:     {settings['extra_packages']}")
    print(f"  Requirements:       {len(settings['requirements'])} pinned package(s)")

    tool_names = [
        getattr(t, "__name__", getattr(t, "name", repr(t)))
        for t in getattr(root_agent, "tools", [])
    ]
    print(f"  Agent Tools:        {tool_names}")

    # enable_tracing=True sends OpenTelemetry traces to Cloud Trace.
    # Requires 'telemetry.traces.write' permission on the service account.
    vertexai.init(
        project=PROJECT_ID,
        location=LOCATION,
        staging_bucket=STAGING_BUCKET,
    )

    app = agent_engines.AdkApp(
        agent=root_agent,
        enable_tracing=True,
    )

    # ---------------------------------------------------------------
    # Load SAP credentials from Secret Manager and build env_vars.
    # ---------------------------------------------------------------
    print("Loading SAP credentials from Secret Manager...")
    sm_client = secretmanager.SecretManagerServiceClient()
    secret_name = (
        args.sap_credentials
        if args.sap_credentials and args.sap_credentials.startswith("projects/")
        else f"projects/{PROJECT_ID}/secrets/{args.sap_credentials or 'sap-credentials'}/versions/latest"
    )
    response = sm_client.access_secret_version(request={"name": secret_name})
    sap_creds = json.loads(response.payload.data.decode("UTF-8"))
    print(f"  Loaded credentials: {list(sap_creds.keys())}")

    # oauth_redirect_uri is excluded because the agent ID (part of the
    # redirect URI) is only assigned AFTER deployment; the agent reads
    # it from Secret Manager at runtime instead.
    RUNTIME_ONLY_KEYS = {"oauth_redirect_uri"}

    env_vars = dict(settings["env_vars"])
    for key, value in sap_creds.items():
        if key in RUNTIME_ONLY_KEYS:
            print(f"  Skipping {key} (read from Secret Manager at runtime)")
            continue
        env_vars[f"SAP_{key.upper()}"] = str(value)

    if "auth_server_url" in sap_creds:
        env_vars["AUTH_SERVER_URL"] = sap_creds["auth_server_url"]

    print(f"  Auth type: {env_vars.get('SAP_AUTH_TYPE', 'basic')}")
    print(f"  Env vars:  {list(env_vars.keys())}")

    # ---------------------------------------------------------------
    # Deploy / Update
    # ---------------------------------------------------------------
    try:
        if args.update:
            print(f"\nUpdating existing Agent Engine: {args.update}")
            remote_app = agent_engines.update(
                resource_name=args.update,
                agent_engine=app,
                requirements=settings["requirements"],
                extra_packages=settings["extra_packages"],
                display_name=settings["display_name"],
                env_vars=env_vars,
                resource_limits=settings["resource_limits"],
                psc_interface_config={
                    "network_attachment": NETWORK_ATTACHMENT,
                },
            )
            print("Update finished!")
        else:
            print("\nCreating new Agent Engine...")
            remote_app = agent_engines.create(
                agent_engine=app,
                requirements=settings["requirements"],
                extra_packages=settings["extra_packages"],
                display_name=settings["display_name"],
                service_account=SERVICE_ACCOUNT,
                env_vars=env_vars,
                resource_limits=settings["resource_limits"],
                psc_interface_config={
                    "network_attachment": NETWORK_ATTACHMENT,
                },
            )
            print("Deployment finished!")

        print(f"Resource Name: {remote_app.resource_name}")

    except Exception as e:
        print(f"Deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
