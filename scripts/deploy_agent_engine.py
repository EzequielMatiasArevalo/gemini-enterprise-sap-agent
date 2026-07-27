"""Deploy an ADK Agent to Vertex AI Agent Engine.

This script deploys an ADK agent with direct Python function tools
(not MCP subprocess) for Agent Engine compatibility.

The agent module is configurable via ``--agent-module``. The script
reads per-agent deployment settings (requirements, resource limits,
display name, extra packages, env vars, service account, min/max
instances, root agent attribute name) from ``<agent_module>/config.yaml``
under the ``deploy:`` key.

Resolution order for every deploy setting:
    1. Explicit CLI argument (highest priority)
    2. ``deploy.<setting>`` in ``<agent_module>/config.yaml``
    3. Built-in fallback

Infrastructure toggles (PSC network attachment, runtime service account,
Secret Manager vs ``deploy.env_vars``) are set in ``deploy:`` in
``config.yaml`` and can be overridden via CLI. Project and region still
come from CLI args / env vars.

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
        help=(
            "Override deploy.staging_bucket / deploy.env_vars.GOOGLE_CLOUD_BUCKET "
            "from config.yaml (default fallback: gs://<PROJECT_ID>_cloudbuild)"
        ),
    )
    parser.add_argument(
        "--service-account",
        default=None,
        help=(
            "Override deploy.service_account from config.yaml. "
            "Service account email or short ID for the Agent Engine "
            "(default: agent-engine-sa@{PROJECT_ID}.iam.gserviceaccount.com)"
        ),
    )
    parser.add_argument(
        "--min-instances",
        type=int,
        default=None,
        help="Override deploy.min_instances from config.yaml.",
    )
    parser.add_argument(
        "--max-instances",
        type=int,
        default=None,
        help="Override deploy.max_instances from config.yaml.",
    )
    parser.add_argument(
        "--use-network-attachment",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Override deploy.use_network_attachment from config.yaml. "
            "When enabled, attaches PSC (see deploy.network_attachment)."
        ),
    )
    parser.add_argument(
        "--network-attachment",
        default=None,
        help=(
            "Override deploy.network_attachment (full resource path or attachment name). "
            "Implies PSC is enabled unless --no-use-network-attachment is set."
        ),
    )
    parser.add_argument(
        "--use-service-account",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Override deploy.use_service_account. When disabled, the Agent Engine "
            "runtime uses the project default identity (no custom SA in the API)."
        ),
    )
    parser.add_argument(
        "--secrets-source",
        choices=("config", "secret_manager"),
        default=None,
        help=(
            "Override deploy.secrets_source: 'config' uses deploy.env_vars only; "
            "'secret_manager' loads JSON from Secret Manager."
        ),
    )
    parser.add_argument(
        "--credentials",
        default=None,
        help=(
            "Override deploy.credentials_secret: Secret Manager secret ID or "
            "full version path (only when secrets_source is secret_manager)."
        ),
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


def _resolve_bool(
    cli_value: Optional[bool], cfg_value: Any, default: bool
) -> bool:
    if cli_value is not None:
        return cli_value
    if cfg_value is not None:
        return bool(cfg_value)
    return default


def _normalize_gcs_uri(raw: str) -> str:
    """Ensure bucket value is a ``gs://`` URI."""
    value = str(raw).strip()
    if not value:
        raise SystemExit("staging_bucket must not be empty.")
    if value.startswith("gs://"):
        return value
    return f"gs://{value}"


def resolve_staging_bucket(
    args: argparse.Namespace,
    deploy_cfg: Dict[str, Any],
    project_id: str,
) -> str:
    """
    Resolve Vertex AI staging bucket for packaging the agent.

    Priority:
        1. ``STAGING_BUCKET`` env var
        2. ``--staging-bucket`` CLI
        3. ``deploy.staging_bucket`` in config.yaml
        4. ``deploy.env_vars.GOOGLE_CLOUD_BUCKET`` in config.yaml
        5. ``gs://<project_id>_cloudbuild``
    """
    if os.getenv("STAGING_BUCKET"):
        return _normalize_gcs_uri(os.environ["STAGING_BUCKET"])
    if args.staging_bucket:
        return _normalize_gcs_uri(args.staging_bucket)

    cfg_bucket = deploy_cfg.get("staging_bucket")
    if cfg_bucket:
        return _normalize_gcs_uri(str(cfg_bucket))

    env_vars = deploy_cfg.get("env_vars") or {}
    if isinstance(env_vars, dict):
        cloud_bucket = env_vars.get("GOOGLE_CLOUD_BUCKET")
        if cloud_bucket:
            return _normalize_gcs_uri(str(cloud_bucket))

    return f"gs://{project_id}_cloudbuild"


def _normalize_network_attachment(
    raw: str, project_id: str, region: str
) -> str:
    raw = raw.strip()
    if raw.startswith("projects/"):
        return raw
    return (
        f"projects/{project_id}/regions/{region}"
        f"/networkAttachments/{raw}"
    )


def resolve_infrastructure_settings(
    args: argparse.Namespace,
    deploy_cfg: Dict[str, Any],
    project_id: str,
    region: str,
) -> Dict[str, Any]:
    """Resolve PSC, runtime SA, and credentials source from config + CLI."""
    use_network_attachment = _resolve_bool(
        args.use_network_attachment,
        deploy_cfg.get("use_network_attachment"),
        default=True,
    )
    if args.network_attachment is not None:
        use_network_attachment = True

    network_attachment_raw = (
        args.network_attachment
        or deploy_cfg.get("network_attachment")
        or "agent-engine-attachment"
    )
    network_attachment = _normalize_network_attachment(
        str(network_attachment_raw), project_id, region
    )

    use_service_account = _resolve_bool(
        args.use_service_account,
        deploy_cfg.get("use_service_account"),
        default=True,
    )
    service_account = args.service_account or deploy_cfg.get("service_account")
    if service_account is not None:
        service_account = str(service_account).strip() or None
        if service_account and not use_service_account:
            use_service_account = True

    credentials_secret = args.credentials or deploy_cfg.get("credentials_secret")
    if credentials_secret is not None:
        credentials_secret = str(credentials_secret).strip() or None

    secrets_source = args.secrets_source or deploy_cfg.get("secrets_source")
    if secrets_source is None:
        secrets_source = (
            "secret_manager"
            if credentials_secret
            else "config"
        )
    if secrets_source not in ("config", "secret_manager"):
        raise SystemExit(
            f"Invalid secrets_source '{secrets_source}'. "
            "Use 'config' or 'secret_manager'."
        )

    if args.credentials and args.secrets_source is None:
        secrets_source = "secret_manager"
    if secrets_source == "secret_manager":
        if not credentials_secret:
            raise SystemExit(
                "secrets_source is 'secret_manager' but no secret was provided. "
                "Set deploy.credentials_secret in config.yaml or pass --credentials."
            )
    else:
        credentials_secret = None

    return {
        "use_network_attachment": use_network_attachment,
        "network_attachment": network_attachment,
        "use_service_account": use_service_account,
        "service_account": service_account,
        "secrets_source": secrets_source,
        "credentials_secret": credentials_secret,
    }


def load_credentials_from_secret_manager(
    credentials_secret: str, project_id: str
) -> Dict[str, Any]:
    sm_client = secretmanager.SecretManagerServiceClient()
    if credentials_secret.startswith("projects/"):
        secret_name = credentials_secret
    else:
        secret_name = (
            f"projects/{project_id}/secrets/{credentials_secret}/versions/latest"
        )
    response = sm_client.access_secret_version(request={"name": secret_name})
    return json.loads(response.payload.data.decode("UTF-8"))


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

    # Autoscaling bounds
    min_instances = (
        args.min_instances
        if args.min_instances is not None
        else deploy_cfg.get("min_instances")
    )
    if min_instances is not None:
        min_instances = int(min_instances)

    max_instances = (
        args.max_instances
        if args.max_instances is not None
        else deploy_cfg.get("max_instances")
    )
    if max_instances is not None:
        max_instances = int(max_instances)

    if (
        min_instances is not None
        and max_instances is not None
        and min_instances > max_instances
    ):
        raise SystemExit(
            f"min_instances ({min_instances}) cannot exceed "
            f"max_instances ({max_instances})."
        )

    return {
        "agent_attr": agent_attr,
        "display_name": display_name,
        "resource_limits": resource_limits,
        "requirements": requirements,
        "extra_packages": extra_packages,
        "env_vars": env_vars,
        "min_instances": min_instances,
        "max_instances": max_instances,
    }


def main() -> None:
    args = parse_args()

    PROJECT_ID = os.getenv("PROJECT_ID") or args.project
    LOCATION = os.getenv("REGION") or args.region

    RUNTIME_ONLY_KEYS = [
        "oauth_redirect_uri"
    ]

    os.environ["PROJECT_ID"] = PROJECT_ID

    cfg = load_config(args.agent_module, args.config)
    deploy_cfg = cfg.get("deploy", {}) or {}
    STAGING_BUCKET = resolve_staging_bucket(args, deploy_cfg, PROJECT_ID)
    infra = resolve_infrastructure_settings(args, deploy_cfg, PROJECT_ID, LOCATION)
    settings = resolve_deploy_settings(args, cfg)

    SERVICE_ACCOUNT = None
    if infra["use_service_account"]:
        SERVICE_ACCOUNT = infra["service_account"] or (
            f"agent-engine-sa@{PROJECT_ID}.iam.gserviceaccount.com"
        )
        if "@" not in SERVICE_ACCOUNT:
            SERVICE_ACCOUNT = (
                f"{SERVICE_ACCOUNT}@{PROJECT_ID}.iam.gserviceaccount.com"
            )

    MIN_INSTANCES = settings["min_instances"]
    MAX_INSTANCES = settings["max_instances"]

    root_agent = load_agent(args.agent_module, settings["agent_attr"])

    print("Initializing Vertex AI SDK...")
    print(f"  Project:            {PROJECT_ID}")
    print(f"  Location:           {LOCATION}")
    print(f"  Staging Bucket:       {STAGING_BUCKET}")
    print(f"  PSC / Attachment:     {infra['use_network_attachment']}")
    if infra["use_network_attachment"]:
        print(f"  Network Attachment:   {infra['network_attachment']}")
    print(f"  Runtime SA (custom):  {infra['use_service_account']}")
    if infra["use_service_account"]:
        print(f"  Service Account:      {SERVICE_ACCOUNT}")
    else:
        print("  Service Account:      (project default — no custom SA in API)")
    print(f"  Secrets source:       {infra['secrets_source']}")
    print(f"  Min Instances:      {MIN_INSTANCES}")
    print(f"  Max Instances:      {MAX_INSTANCES}")
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
    # Build env_vars (config.yaml and/or Secret Manager).
    # ---------------------------------------------------------------
    env_vars = dict(settings["env_vars"])

    if infra["secrets_source"] == "secret_manager":
        print("Loading credentials from Secret Manager...")
        try:
            creds = load_credentials_from_secret_manager(
                infra["credentials_secret"], PROJECT_ID
            )
            print(f"  Loaded credentials: {list(creds.keys())}")
        except Exception as e:
            secret_ref = infra["credentials_secret"]
            print(f"""
                Error loading credentials: {e}
                Please check if the secret exists and you have the necessary permissions.
                If secret is not found, check Readme.md to create the first version of the secret.
                You can check the secret name and your permissions with:
                    gcloud secrets describe {secret_ref} --project {PROJECT_ID}
            """)
            sys.exit(1)
        for key, value in creds.items():
            if key in RUNTIME_ONLY_KEYS:
                print(f"  Skipping {key} (read from Secret Manager at runtime)")
                continue
            env_vars[key.upper()] = str(value)
    else:
        print("Using credentials from deploy.env_vars in config.yaml (no Secret Manager).")
        print(f"  Env var keys: {sorted(env_vars.keys())}")

    # if "auth_server_url" in creds:
    #     env_vars["AUTH_SERVER_URL"] = creds["auth_server_url"]

    # print(f"  Auth type: {env_vars.get('SAP_AUTH_TYPE', 'basic')}")
    # print(f"  Env vars:  {list(env_vars.keys())}")

    # ---------------------------------------------------------------
    # Deploy / Update
    # ---------------------------------------------------------------
    deploy_kwargs: Dict[str, Any] = {
        "requirements": settings["requirements"],
        "extra_packages": settings["extra_packages"],
        "display_name": settings["display_name"],
        "env_vars": env_vars,
        "resource_limits": settings["resource_limits"],
    }
    if infra["use_service_account"]:
        deploy_kwargs["service_account"] = SERVICE_ACCOUNT
    if infra["use_network_attachment"]:
        deploy_kwargs["psc_interface_config"] = {
            "network_attachment": infra["network_attachment"],
        }
    if MIN_INSTANCES is not None:
        deploy_kwargs["min_instances"] = MIN_INSTANCES
    if MAX_INSTANCES is not None:
        deploy_kwargs["max_instances"] = MAX_INSTANCES

    try:
        if args.update:
            print(f"\nUpdating existing Agent Engine: {args.update}")
            remote_app = agent_engines.update(
                resource_name=args.update,
                agent_engine=app,
                **deploy_kwargs,
            )
            print("Update finished!")
        else:
            print("\nCreating new Agent Engine...")
            remote_app = agent_engines.create(
                agent_engine=app,
                **deploy_kwargs,
            )
            print("Deployment finished!")

        print(f"Resource Name: {remote_app.resource_name}")

    except Exception as e:
        print(f"Deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
