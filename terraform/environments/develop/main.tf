module "sap_agent" {
  source = "../../modules/sap_agent"

  providers = {
    google-beta = google-beta
  }

  project_id  = var.project_id
  region      = var.region
  environment = var.environment
  repo_root   = var.repo_root

  vpc_mode              = var.vpc_mode
  vpc_name              = var.vpc_name
  create_consumer_subnet = var.create_consumer_subnet
  consumer_subnet_range  = var.consumer_subnet_range

  enable_psc                      = var.enable_psc
  sap_ip                          = var.sap_ip
  enable_psc_nat                  = var.enable_psc_nat
  enable_psc_private_dns          = var.enable_psc_private_dns
  psc_dns_record_sets             = var.psc_dns_record_sets
  enable_psc_to_consumer_firewall = var.enable_psc_to_consumer_firewall
  enable_iap_ssh_firewall         = var.enable_iap_ssh_firewall

  deploy_agent_engine        = var.deploy_agent_engine
  agent_engine_resource_name = var.agent_engine_resource_name
  agent_deploy_revision      = var.agent_deploy_revision
  agent_module               = var.agent_module
  agent_engine_env_vars      = var.agent_engine_env_vars

  aiplatform_iam_wait_seconds = var.aiplatform_iam_wait_seconds
  service_account_id          = var.agent_service_account
  sap_secret_id               = var.sap_credentials_secrets
  staging_bucket_name         = var.staging_bucket_name
  network_attachment_name     = var.network_attachment_name
}
