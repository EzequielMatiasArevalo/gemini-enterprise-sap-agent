# SAP ABAP Agent on GCP — Terraform + Vertex AI Agent Engine

End-to-end deployment of an ADK-based **SAP ABAP code agent** to **Vertex AI Agent Engine**, with all GCP infrastructure managed by Terraform.

The Terraform layout mirrors the legacy `scripts/setup_gcp_prerequisites.sh` and `scripts/setup_psc_infrastructure.sh` bash scripts, using **native Google provider resources** wherever possible. A single `null_resource` wraps `scripts/deploy_agent_engine.py`, since Vertex AI Agent Engine (Reasoning Engine) is not yet exposed as a stable Terraform resource.

---

## Repository layout

```
.
├── sap_abap_agent_v2/                 # Agent package (ADK Agent + tools + config)
│   ├── agent.py                       # root_agent definition
│   ├── tools.py                       # SAP ADT API tools
│   └── config.yaml                    # Deploy-time settings (requirements, scaling, env vars, …)
├── scripts/
│   ├── deploy_agent_engine.py         # Generic deploy script (driven by config.yaml)
│   └── test_agent.py                  # Smoke-test a deployed Agent Engine
└── terraform/
    ├── bootstrap/setup_remote_state.sh    # Create GCS state bucket + scaffold an environment
    ├── modules/
    │   ├── apis/                          # google_project_service
    │   ├── vpc/                           # Create new VPC or reuse existing
    │   ├── service_account/               # agent-engine-sa + IAM
    │   ├── ai_platform_agents/            # Vertex AI service agents (PSC peering)
    │   ├── staging_bucket/                # GCS staging bucket for Agent Engine
    │   ├── sap_secret/                    # sap-credentials secret shell
    │   ├── psc/                           # Private Service Connect consumer stack
    │   ├── agent_engine_deploy/           # null_resource → deploy_agent_engine.py
    │   └── sap_agent/                     # Composite module (one call per project/env)
    └── environments/
        └── example/                        # Template; copy per project/environment
```

---

## Quick start

## 0. Set up the Python environment

```bash
uv venv --python 3.11 .venv
source .venv/bin/activate
uv sync
```

## 1. Bootstrap the Terraform remote state (GCS)

The bootstrap script creates the state bucket **and** scaffolds a new environment folder (a full copy of `environments/example`) named after the environment you pass:

```bash
chmod +x terraform/bootstrap/setup_remote_state.sh
./terraform/bootstrap/setup_remote_state.sh <PROJECT_ID> [BUCKET_NAME] [ENVIRONMENT]
```

Example:

```bash
./terraform/bootstrap/setup_remote_state.sh eleven-analytics-agents tf-state-sap-agent develop
```

This will:

- Enable `storage.googleapis.com` on the project.
- Create `gs://tf-state-sap-agent` (defaults to `gs://<PROJECT_ID>-tfstate` if no bucket name is provided), with versioning enabled.
- Copy `terraform/environments/example` to `terraform/environments/develop`.
- Generate `terraform/environments/develop/backend.gcs.tfbackend` pointing at the bucket.

Override the default state prefix by exporting `STATE_PREFIX` before running the script (default: `sap-agent/dev`).

## 2. Configure the environment

```bash
cd terraform/environments/develop
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set, at minimum:

- `project_id` — target GCP project.
- `region` — GCP region (default: `us-central1`).
- `vpc_mode` — `"existing"` (default) or `"create"`.
- `vpc_name` — VPC to reuse or create.
- `sap_ip` — SAP host IP or URL (used by the PSC firewall rule).
- `agent_module` — Python package of the agent to deploy (default: `sap_abap_agent_v2`).
- `sap_credentials_secrets` — Secret Manager secret holding SAP credentials.
- `agent_service_account` — short ID for the Agent Engine service account.
- `staging_bucket_name` — GCS bucket name used as the Agent Engine staging area.
- `network_attachment_name` — name of the PSC network attachment used by Agent Engine.

## 3. Initialize and apply

```bash
terraform init -backend-config=backend.gcs.tfbackend
terraform plan
terraform apply
```

When this finishes, all prerequisite infrastructure is in place. Terraform also creates the (empty) `sap-credentials` secret — you still need to populate it before deploying the agent.

## 4. Add SAP credentials to Secret Manager

Terraform creates the secret shell only. Add a version with your SAP connection payload before enabling the Agent Engine deploy:

```bash
echo '{ "SAP_URL": "http://IP:PORT", "SAP_USERNAME": "user", "SAP_PASSWORD": "password", "SAP_CLIENT": "300" }' | \
  gcloud secrets versions add sap-agent-abap --data-file=-
```

> If you changed `sap_credentials_secrets` in `terraform.tfvars`, replace `sap-agent-abap` with your value.

The deploy script reads this secret, lowercases each key, and exposes it to the container as `SAP_<KEY>` env vars (`SAP_URL`, `SAP_USERNAME`, `SAP_PASSWORD`, …). If the payload includes `auth_server_url`, it is also forwarded as `AUTH_SERVER_URL`. The key `oauth_redirect_uri` is intentionally skipped at deploy time — the agent reads it from Secret Manager at runtime, because the redirect URI depends on the Agent Engine resource ID, which only exists after the first deploy.

## 5. Deploy the Agent Engine

Once the secret has a version, flip the deploy flag in `terraform.tfvars` and bump the revision to force a re-run on subsequent applies:

```hcl
deploy_agent_engine   = true
agent_deploy_revision = "2"   # bump to force redeploy
```

Then run:

```bash
terraform apply
```

Terraform invokes `scripts/deploy_agent_engine.py` with:

```
--project            <project_id>
--region             <region>
--staging-bucket     gs://<staging_bucket_name>
--service-account    <email>                  # optional; from agent_service_account when set
--network-attachment projects/<project_id>/regions/<region>/networkAttachments/<network_attachment_name>
--sap-credentials    projects/<project_id>/secrets/<sap_credentials_secrets>/versions/latest
--agent-module       <agent_module>
--env-vars           KEY=value,KEY=value      # only when agent_engine_env_vars is non-empty
--update             <resource_name>          # only when agent_engine_resource_name is set
```

Infrastructure flags (`project`, `region`, staging bucket, network attachment, SAP secret, optional `--service-account` from Terraform) are always passed by Terraform. Deploy-time **agent** settings (display name, resource limits, service account, min/max instances, Python requirements, extra packages, env vars) are loaded from `<agent_module>/config.yaml` unless overridden on the CLI — see the next section.

Requirements on the machine running `terraform apply`:

- The Python environment from step 0 (`uv sync`) on `PATH`, or set `python_interpreter` in the module to a specific binary.
- Application Default Credentials with permission to create Vertex AI Reasoning Engines and read Secret Manager.

## Test It

A test script is available inside the `scripts` directory.

```bash
export AGENT_ENGINE_RESOURCE=<RESOURCE_NAME>
uv run scripts/test_agent.py
```

If you do not know the resource name, run the script without setting `AGENT_ENGINE_RESOURCE`.
The script will list all available agents for you.

```bash
unset AGENT_ENGINE_RESOURCE
uv run scripts/test_agent.py
```

Then repeat the previous step using the desired resource name.

---

## Optional: Per-agent configuration: `<agent_module>/config.yaml`

`scripts/deploy_agent_engine.py` is **generic**: it imports `<agent_module>.agent`, picks up the root agent attribute, and reads every deploy setting from a single YAML file located at `<agent_module>/config.yaml`.

Resolution order for every deploy setting (highest priority first):

1. Explicit CLI argument on `deploy_agent_engine.py`.
2. `deploy.<setting>` in `<agent_module>/config.yaml`.
3. Built-in fallback inside the script.

Example `sap_abap_agent_v2/config.yaml`:

```yaml
agent_name: 'sap_abap_agent_v2'
agent_display_name: 'SAP ABAP ADK Agent V2'
agent_description: 'SAP ABAP Code Agent in Google Cloud'

deploy:
  # Display name shown in the Vertex AI Agent Engine console.
  display_name: 'SAP Agent'

  # Runtime service account (email or short ID). When omitted, the deploy
  # script uses agent-engine-sa@<project>.iam.gserviceaccount.com.
  # service_account: 'agent-engine-sa'

  # Autoscaling bounds (optional; Agent Engine defaults apply when omitted).
  min_instances: 1
  max_instances: 10

  # Attribute name of the root agent inside <agent_module>/agent.py.
  agent_attr: 'root_agent'

  # Container resource limits.
  # Supported: cpu in {"1","2","4","6","8"}, memory in "1Gi" .. "32Gi".
  resource_limits:
    cpu: '4'
    memory: '8Gi'

  # Local packages bundled into the Agent Engine container.
  # Defaults to ["./<agent_module>"] when omitted.
  extra_packages:
    - './sap_abap_agent_v2'

  # Non-secret env vars. SAP_* and AUTH_SERVER_URL are injected from
  # Secret Manager by the deploy script and must NOT be listed here.
  env_vars:
    SAP_LANGUAGE: 'EN'
    GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY: 'true'
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: 'true'

  # Python requirements installed inside the container.
  requirements:
    - 'google-cloud-aiplatform[adk,agent_engines]>=1.128.0'
    - 'google-adk>=1.27.0'
    - 'google-cloud-secret-manager>=2.16.0'
    - 'pydantic>=2.5.0'
    # …
```

### Supported `deploy.*` keys

| Key               | Type             | Purpose                                                                                       |
|-------------------|------------------|-----------------------------------------------------------------------------------------------|
| `display_name`    | string           | Display name shown in the Agent Engine console.                                               |
| `service_account` | string           | Runtime service account (email or short ID). Default: `agent-engine-sa@<project>.iam.gserviceaccount.com`. |
| `min_instances`   | int              | Minimum number of Agent Engine instances (autoscaling). Optional.                             |
| `max_instances`   | int              | Maximum number of Agent Engine instances (autoscaling). Optional.                             |
| `agent_attr`      | string           | Attribute name of the root agent inside `<agent_module>/agent.py` (default: `root_agent`).    |
| `resource_limits` | map (cpu/memory) | Container CPU and memory.                                                                     |
| `extra_packages`  | list[string]     | Local paths bundled into the container. Defaults to `["./<agent_module>"]`.                   |
| `env_vars`        | map[str, str]    | Non-secret env vars merged into the deployment.                                               |
| `requirements`    | list[string]     | Pip requirements installed inside the container. **Required** (no built-in default).          |

CLI overrides for the same settings: `--display-name`, `--service-account`, `--min-instances`, `--max-instances`, `--agent-attr`, `--resource-limits`, `--requirements`, `--extra-packages`, `--env-vars`.

### Deploying a different agent

To deploy a separate agent package, create a sibling Python module that exposes an `agent.py` with a root agent and its own `config.yaml`, then set:

```hcl
agent_module = "my_other_agent"
```

The deploy script imports `my_other_agent.agent`, reads `my_other_agent/config.yaml`, and ships only that package as the extra package by default. The same Terraform infrastructure (service account, staging bucket, PSC attachment, secret) is reused.

You can also invoke the script directly:

```bash
python scripts/deploy_agent_engine.py \
  --project <PROJECT_ID> \
  --agent-module my_other_agent

# Override scaling or service account from config.yaml
python scripts/deploy_agent_engine.py \
  --project <PROJECT_ID> \
  --min-instances 1 \
  --max-instances 5 \
  --service-account sap-agent-abap@<PROJECT_ID>.iam.gserviceaccount.com

# Another example

 python3 scripts/deploy_agent_engine.py \
  --project "eleven-analytics-agents" \
  --region "us-central1" \
  --min-instances "1" \
  --max-instances "5" \
  --staging-bucket "gs://staging-sap-agent-abap-develop" \
  --agent-module "sap_abap_agent_v2" \
  --service-account "sap-agent-abap@eleven-analytics-agents.iam.gserviceaccount.com" \
  --network-attachment "projects/eleven-analytics-agents/regions/us-central1/networkAttachments/agent-engine-attachment" \
  --credentials "projects/eleven-analytics-agents/secrets/sap-agent-abap/versions/latest" 
```

---

## Terraform variables (composite `sap_agent` module)

The composite module lives at `terraform/modules/sap_agent`. The most relevant variables for day-to-day use are listed below; see `terraform/modules/sap_agent/variables.tf` for the full set.

### Core

| Variable                          | Default                       | Purpose                                                                 |
|-----------------------------------|-------------------------------|-------------------------------------------------------------------------|
| `project_id`                      | —                             | Target GCP project ID. **Required.**                                    |
| `region`                          | `us-central1`                 | GCP region.                                                             |
| `environment`                     | `dev`                         | Label used in state prefixes and names.                                 |
| `repo_root`                       | auto-detected                 | Absolute path to repo root (only needed when `deploy_agent_engine`).    |
| `apis`                            | curated list                  | Override the set of GCP APIs to enable.                                 |
| `service_account_id`              | `agent-engine-sa`             | Short ID of the runtime service account (also exposed as `agent_service_account` in `environments/develop/variables.tf`). |
| `service_account_roles`           | curated list                  | IAM roles bound to the service account.                                 |
| `staging_bucket_name`             | `null` (auto-named)           | GCS staging bucket used by Agent Engine (`gs://<name>`).                |
| `sap_secret_id`                   | `sap-credentials`             | Secret Manager secret ID for SAP credentials (alias: `sap_credentials_secrets`). |

### VPC

| Variable                | Default                     | Purpose                                                                |
|-------------------------|-----------------------------|------------------------------------------------------------------------|
| `vpc_mode`              | `existing`                  | `existing` reuses `vpc_name`; `create` provisions a new custom VPC.    |
| `vpc_name`              | `sap-cal-default-network`   | Name of the VPC to reuse or create.                                    |
| `create_consumer_subnet`| `false`                     | Create a workload subnet inside the VPC (auto-enabled for `create` + PSC NAT). |
| `consumer_subnet_name`  | `consumer-subnet`           | Name of the consumer subnet.                                           |
| `consumer_subnet_range` | `10.10.10.0/28`             | CIDR of the consumer subnet.                                           |

### Private Service Connect

| Variable                          | Default                  | Purpose                                                              |
|-----------------------------------|--------------------------|----------------------------------------------------------------------|
| `enable_psc`                      | `true`                   | Deploy the PSC consumer stack (subnet, attachment, firewall to SAP). |
| `psc_subnet_name`                 | `psc-attachment-subnet`  | Name of the PSC attachment subnet.                                   |
| `psc_subnet_range`                | `192.168.10.0/28`        | CIDR of the PSC attachment subnet.                                   |
| `network_attachment_name`         | `agent-engine-attachment`| Name of the PSC network attachment exposed to Agent Engine.          |
| `sap_ip`                          | `10.142.0.5`             | SAP host IP / URL used in the PSC → SAP firewall rule.               |
| `enable_psc_nat`                  | `false`                  | Cloud Router + Cloud NAT for egress through the consumer VPC.        |
| `enable_psc_private_dns`          | `false`                  | Private DNS zone for Agent Engine DNS peering.                       |
| `psc_dns_zone_name`               | `psc-private-dns`        | Cloud DNS managed-zone name.                                         |
| `psc_dns_name`                    | `sap.internal.`          | Private DNS zone domain (trailing dot required).                     |
| `psc_dns_record_sets`             | `{}`                     | DNS records (hostname → A record) inside the private zone.           |
| `enable_psc_to_consumer_firewall` | `false`                  | Firewall: PSC subnet → consumer workload subnet.                     |
| `enable_iap_ssh_firewall`         | `false`                  | Firewall: IAP → consumer subnet SSH (proxy VM administration).       |
| `aiplatform_iam_wait_seconds`     | `90`                     | Wait for Vertex AI service-agent IAM propagation before deploying.   |

### Agent Engine deploy

| Variable                     | Default               | Purpose                                                                                 |
|------------------------------|-----------------------|-----------------------------------------------------------------------------------------|
| `deploy_agent_engine`        | `false`               | Toggle running `scripts/deploy_agent_engine.py` from a `null_resource`.                 |
| `agent_module`               | —                     | Python package of the agent to deploy. **Required when deploying.**                     |
| `agent_engine_resource_name` | `null`                | Update an existing Agent Engine resource instead of creating a new one.                 |
| `agent_deploy_revision`      | `"1"`                 | Bump to force the deploy provisioner to rerun.                                          |
| `agent_engine_env_vars`      | `{}`                  | Extra non-secret env vars merged on top of `deploy.env_vars` from `config.yaml`. User-supplied keys win. |
| `python_interpreter`         | `python3`             | Python binary used to run the deploy script.                                            |

> Agent Engine **content** settings (`display_name`, `resource_limits`, `requirements`, `extra_packages`, base `env_vars`, `service_account`, `min_instances`, `max_instances`) live in `<agent_module>/config.yaml`, not in `terraform.tfvars`. Terraform may still pass `--service-account` when `agent_service_account` is set (CLI wins over config).

### Example `terraform.tfvars` (existing VPC, no PSC)

```hcl
project_id  = "eleven-analytics-agents"
region      = "us-central1"
environment = "dev"

vpc_mode                = "existing"
vpc_name                = "sap-agent-vpc"
network_attachment_name = "agent-engine-attachment"
agent_service_account   = "sap-agent-abap"
sap_credentials_secrets = "sap-agent-abap"
agent_module            = "sap_abap_agent_v2"
staging_bucket_name     = "staging-sap-agent-abap-develop"

enable_psc     = false
enable_psc_nat = false

sap_ip = "http://ecc-xe1.example.com/sap/bc/adt?saml2=disabled"

# Optional: extra runtime env vars merged on top of deploy.env_vars from config.yaml.
# agent_engine_env_vars = {
#   MY_FLAG = "true"
# }

aiplatform_iam_wait_seconds = 45

deploy_agent_engine   = true
agent_deploy_revision = "4"
```

### Example `terraform.tfvars` (new VPC + PSC)

See `terraform/environments/example/terraform.tfvars.create-vpc-psc.example`:

```hcl
project_id  = "eleven-analytics-agents"
region      = "us-central1"
environment = "dev"

vpc_mode               = "create"
vpc_name               = "sap-agent-vpc"
create_consumer_subnet = true
consumer_subnet_range  = "10.10.10.0/28"

enable_psc                      = true
enable_psc_nat                  = true
enable_psc_to_consumer_firewall = true
enable_iap_ssh_firewall         = true

enable_psc_private_dns = true
psc_dns_record_sets = {
  "proxy-vm" = {
    type    = "A"
    ttl     = 300
    rrdatas = ["10.10.10.2"]
  }
}

sap_ip = "10.142.0.5"

deploy_agent_engine = false
```

---

## Reusing the module across projects and environments

Copy `terraform/environments/example` to `terraform/environments/<env>/` (the bootstrap script does this for you) and override:

| File                        | What to change                                                |
|-----------------------------|---------------------------------------------------------------|
| `backend.gcs.tfbackend`     | Unique `prefix` per project/env (e.g. `sap-agent/acme/dev`).  |
| `terraform.tfvars`          | Target `project_id`, `region`, VPC, secrets, agent module.    |
| `main.tf` `module "sap_agent"` | Path is unchanged: `../../modules/sap_agent`.              |

Example state prefixes:

- `sap-agent/acme-corp/dev`
- `sap-agent/contoso/prod`

---

## VPC: create or reuse

| `vpc_mode`  | Behavior                                                                 |
|-------------|--------------------------------------------------------------------------|
| `existing`  | Look up `vpc_name` (default: `sap-cal-default-network`).                 |
| `create`    | Provision a custom-mode VPC named `vpc_name`.                            |

`create_consumer_subnet = true` adds a workload subnet (recommended when you need an explicit proxy VM in the consumer VPC).

## Private Service Connect

When `enable_psc = true`, the `psc` module deploys the **consumer** side of the [Vertex AI Agent Engine PSC Interface](https://cloud.google.com/vertex-ai/docs/general/vpc-psc-i-setup):

| Resource                                        | Always | Optional behind...                  |
|-------------------------------------------------|--------|-------------------------------------|
| PSC attachment subnet (`192.168.10.0/28`)       | yes    | —                                   |
| `google_compute_network_attachment`             | yes    | —                                   |
| Firewall PSC → SAP (`sap_ip`)                   | yes    | —                                   |
| Firewall PSC → consumer subnet                  | no     | `enable_psc_to_consumer_firewall`   |
| Cloud Router + Cloud NAT                        | no     | `enable_psc_nat`                    |
| Private Cloud DNS zone + records                | no     | `enable_psc_private_dns`            |
| IAP SSH firewall to consumer subnet             | no     | `enable_iap_ssh_firewall`           |

The output `network_attachment_id` is passed to Agent Engine as `psc_interface_config.network_attachment`.

- **On-prem SAP (existing VPC):** start from `terraform.tfvars.example` with `vpc_mode = "existing"`.
- **New VPC + proxy / internet egress:** start from `terraform.tfvars.create-vpc-psc.example`.

---

## What Terraform manages vs. what the deploy script handles

| Resource / step                       | Terraform                                                                 | Notes                                                                 |
|---------------------------------------|---------------------------------------------------------------------------|-----------------------------------------------------------------------|
| GCP APIs                              | `google_project_service`                                                  | Same list as the legacy setup script.                                 |
| VPC + subnets                         | `modules/vpc`                                                             | Create or reuse.                                                      |
| `agent-engine-sa` + IAM               | `google_service_account` + `google_project_iam_member`                    | Roles configurable via `service_account_roles`.                       |
| Vertex AI service agents              | `google_project_service_identity` + `google_project_iam_member`           | Grants `networkAdmin`, `viewer`, `dns.peer` to `service-…@gcp-sa-aiplatform` for PSC. |
| Staging bucket                        | `google_storage_bucket`                                                   | Configurable via `staging_bucket_name`.                               |
| `sap-credentials` secret (shell)      | `google_secret_manager_secret`                                            | Version is added manually with `gcloud secrets versions add`.         |
| PSC subnet + attachment + firewalls   | `modules/psc`                                                             | Consumer side of the Agent Engine PSC Interface.                      |
| Cloud NAT                             | `google_compute_router_nat`                                               | Optional (`enable_psc_nat`).                                          |
| Private DNS                           | `google_dns_managed_zone`                                                 | Optional (`enable_psc_private_dns`).                                  |
| Agent Engine deployment               | `null_resource` → `scripts/deploy_agent_engine.py`                        | Driven by `<agent_module>/config.yaml`.                               |

---

## Testing a deployed Agent Engine

After `terraform apply` finishes the deploy, you can smoke-test the Agent Engine with `scripts/test_agent.py`. The script reads the target resource name from the `AGENT_ENGINE_RESOURCE` environment variable, prints the agent's metadata, and streams a sample query through it.

### 1. Authenticate and pick a project/region

The script uses Application Default Credentials and the default Vertex AI client. Make sure you are authenticated against the same project and region where the Agent Engine was deployed:

```bash
gcloud auth application-default login
gcloud config set project <PROJECT_ID>
export GOOGLE_CLOUD_PROJECT=<PROJECT_ID>
export GOOGLE_CLOUD_LOCATION=us-central1
```

### 2. Discover the resource name

If you don't know the resource name, run the script without `AGENT_ENGINE_RESOURCE` set — it will list every Agent Engine the caller can see in the active project:

```bash
unset AGENT_ENGINE_RESOURCE
python scripts/test_agent.py
```

Sample output:

```
====================  ERROR  ====================
AGENT_ENGINE_RESOURCE is not set. Please set it in the environment variables.
Available agents:
--------------------
Resource Name: projects/123/locations/us-central1/reasoningEngines/456
Display Name:  SAP Agent
```

Terraform also surfaces the resource name in its plan output for the `null_resource.deploy_agent_engine` provisioner, and the deploy script prints it at the end of every run (`Resource Name: projects/.../reasoningEngines/...`).

### 3. Run the smoke test

```bash
export AGENT_ENGINE_RESOURCE="projects/<PROJECT_NUMBER>/locations/<REGION>/reasoningEngines/<ID>"
python scripts/test_agent.py
```

You should see a banner with the agent's display name, resource name, and last update timestamp, followed by streamed events from the test query (`"Hi, how can you help me?"`). Anything else (auth errors, 404 on the resource, IAM denials) indicates a misconfiguration.

To exercise tool-calling end-to-end, edit the `message` argument inside `scripts/test_agent.py` to a domain-specific prompt — for example, asking the SAP agent to fetch an ABAP program or search for an object.

---

## IAM for the Terraform operator

The identity running `terraform apply` needs at least:

- Project Editor (or granular equivalents for each module's resources).
- `roles/storage.objectAdmin` on the Terraform state bucket.
- `roles/aiplatform.user` and `roles/secretmanager.secretAccessor` for the deploy provisioner.

---

## Related scripts

| Legacy script                               | Terraform equivalent                                                                                  |
|---------------------------------------------|-------------------------------------------------------------------------------------------------------|
| `scripts/setup_gcp_prerequisites.sh`        | `modules/apis`, `modules/service_account`, `modules/ai_platform_agents`, `modules/staging_bucket`, `modules/sap_secret` |
| `scripts/setup_psc_infrastructure.sh`       | `modules/psc`                                                                                         |
| `scripts/deploy_agent_engine.py`            | `modules/agent_engine_deploy` (when `deploy_agent_engine = true`)                                     |





uv run python scripts/deploy_agent_engine.py \
  --project eleven-analytics-agents \
  --region us-central1


uv run python scripts/deploy_agent_engine.py \
  --project eleven-analytics-agents \
  --region us-central1 \
  --staging-bucket gs://ce-sap-latam-genai-demo-agent-engine-deploy \
  --secrets-source config \
  --update "projects/NUMERO/locations/us-central1/reasoningEngines/ID"