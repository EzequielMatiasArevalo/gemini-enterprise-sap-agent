data "google_project" "current" {
  project_id = var.project_id
}

locals {
  repo_root = coalesce(var.repo_root, abspath("${path.module}/../../.."))

  default_apis = [
    "compute.googleapis.com",
    "aiplatform.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "dns.googleapis.com",
    "servicenetworking.googleapis.com",
  ]

  apis = coalesce(var.apis, local.default_apis)

  default_sa_roles = [
    "roles/aiplatform.user",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectViewer",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/serviceusage.serviceUsageConsumer",
  ]

  service_account_roles = coalesce(var.service_account_roles, local.default_sa_roles)

  # Auto-enable consumer subnet + PSC→consumer firewall when creating a new VPC for PSC proxy path
  create_consumer_subnet = var.create_consumer_subnet || (var.vpc_mode == "create" && var.enable_psc_nat)

  psc_consumer_subnet_range = local.create_consumer_subnet ? var.consumer_subnet_range : null

  enable_psc_to_consumer_firewall = var.enable_psc_to_consumer_firewall || (
    var.enable_psc && local.create_consumer_subnet && var.enable_psc_nat
  )

  # Auto-derived runtime env vars for the Agent Engine container.
  # Override any of these by setting the same key in var.agent_engine_env_vars.
  default_agent_engine_env_vars = {}

  agent_engine_env_vars = merge(
    local.default_agent_engine_env_vars,
    var.agent_engine_env_vars,
  )
}

module "apis" {
  source = "../apis"

  project_id = var.project_id
  apis       = local.apis
}

module "vpc" {
  source = "../vpc"

  project_id = var.project_id
  region     = var.region

  vpc_mode   = var.vpc_mode
  vpc_name   = var.vpc_name

  create_consumer_subnet  = local.create_consumer_subnet
  consumer_subnet_name    = var.consumer_subnet_name
  consumer_subnet_range   = var.consumer_subnet_range

  depends_on = [module.apis]
}

module "service_account" {
  source = "../service_account"

  project_id = var.project_id
  account_id = var.service_account_id
  roles      = local.service_account_roles

  depends_on = [module.apis]
}

module "ai_platform_agents" {
  source = "../ai_platform_agents"

  providers = {
    google-beta = google-beta
  }

  project_id     = var.project_id
  project_number = data.google_project.current.number

  depends_on = [module.apis]
}

# Allow project IAM bindings on the Vertex AI service agent to propagate before deploy.
resource "time_sleep" "aiplatform_iam_propagation" {
  count = var.deploy_agent_engine ? 1 : 0

  create_duration = "${var.aiplatform_iam_wait_seconds}s"

  depends_on = [
    module.ai_platform_agents,
    module.psc,
  ]
}

module "staging_bucket" {
  source = "../staging_bucket"

  project_id  = var.project_id
  region      = var.region
  bucket_name = var.staging_bucket_name

  depends_on = [module.apis]
}

module "secret" {
  source = "../secret"

  project_id = var.project_id
  secret_id  = var.secret_id

  depends_on = [module.apis]
}

module "psc" {
  count  = var.enable_psc ? 1 : 0
  source = "../psc"

  project_id   = var.project_id
  region       = var.region
  network_id   = module.vpc.network_id
  network_name = module.vpc.network_name

  psc_subnet_name   = var.psc_subnet_name
  psc_subnet_range  = var.psc_subnet_range
  attachment_name   = var.network_attachment_name
  psc_ip            = var.psc_ip

  consumer_subnet_range           = local.psc_consumer_subnet_range
  create_psc_to_consumer_firewall = local.enable_psc_to_consumer_firewall

  enable_cloud_nat         = var.enable_psc_nat
  enable_private_dns       = var.enable_psc_private_dns
  dns_zone_name            = var.psc_dns_zone_name
  dns_name                 = var.psc_dns_name
  dns_record_sets          = var.psc_dns_record_sets

  enable_iap_ssh_firewall = var.enable_iap_ssh_firewall

  depends_on = [module.apis, module.ai_platform_agents, module.vpc]
}

module "agent_engine_deploy" {
  source = "../agent_engine_deploy"

  enabled                    = var.deploy_agent_engine
  project_id                 = var.project_id
  region                     = var.region
  repo_root                  = local.repo_root
  staging_bucket_url         = module.staging_bucket.url
  python_interpreter         = var.python_interpreter
  agent_engine_resource_name = var.agent_engine_resource_name
  deploy_revision            = var.agent_deploy_revision

  service_account          = module.service_account.email
  network_attachment       = var.enable_psc ? module.psc[0].network_attachment_id : "projects/${var.project_id}/regions/${var.region}/networkAttachments/${var.network_attachment_name}"

  credentials_secret   = "projects/${var.project_id}/secrets/${var.secret_id}/versions/latest"
  agent_module             = var.agent_module
  extra_env_vars           = local.agent_engine_env_vars

  depends_on = [
    module.service_account,
    module.staging_bucket,
    module.secret,
    module.ai_platform_agents,
    module.vpc,
    module.psc,
    time_sleep.aiplatform_iam_propagation,
  ]
}
