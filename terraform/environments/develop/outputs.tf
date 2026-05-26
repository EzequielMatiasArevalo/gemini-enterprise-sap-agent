output "vpc_mode" {
  description = "VPC create vs existing."
  value       = module.sap_agent.vpc_mode
}

output "vpc_network_name" {
  description = "VPC used for PSC."
  value       = module.sap_agent.vpc_network_name
}

output "service_account_email" {
  description = "Agent Engine runtime service account."
  value       = module.sap_agent.service_account_email
}

output "staging_bucket_url" {
  description = "GCS staging bucket for Agent Engine deployments."
  value       = module.sap_agent.staging_bucket_url
}

output "sap_secret_id" {
  description = "Secret Manager secret ID (add a version before deploy)."
  value       = module.sap_agent.sap_secret_id
}

output "network_attachment_id" {
  description = "PSC network attachment for Agent Engine psc_interface_config."
  value       = module.sap_agent.network_attachment_id
}

output "psc_subnet_range" {
  description = "PSC attachment subnet CIDR."
  value       = module.sap_agent.psc_subnet_range
}

output "project_number" {
  value = module.sap_agent.project_number
}
