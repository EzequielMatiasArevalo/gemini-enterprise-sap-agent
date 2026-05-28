output "project_id" {
  value = var.project_id
}

output "project_number" {
  value = data.google_project.current.number
}

output "region" {
  value = var.region
}

output "environment" {
  value = var.environment
}

output "vpc_mode" {
  description = "Whether VPC was created or reused."
  value       = module.vpc.vpc_mode
}

output "vpc_network_name" {
  description = "VPC network name."
  value       = module.vpc.network_name
}

output "consumer_subnet_range" {
  description = "Consumer workload subnet CIDR (if created)."
  value       = module.vpc.consumer_subnet_range
}

output "service_account_email" {
  value = module.service_account.email
}

output "staging_bucket_url" {
  value = module.staging_bucket.url
}

output "secret_id" {
  value = module.secret.secret_id
}

output "network_attachment_id" {
  description = "PSC network attachment ID for Agent Engine (null if PSC disabled)."
  value       = var.enable_psc ? module.psc[0].network_attachment_id : null
}

output "psc_subnet_range" {
  value = var.enable_psc ? module.psc[0].psc_subnet_range : null
}

output "cloud_nat_enabled" {
  value = var.enable_psc && var.enable_psc_nat
}

output "private_dns_zone_name" {
  value = var.enable_psc && var.enable_psc_private_dns ? module.psc[0].private_dns_zone_name : null
}

output "ai_platform_service_agents" {
  description = "AI Platform service agents that received IAM bindings."
  value       = module.ai_platform_agents.bound_service_agents
}

output "ai_platform_service_agents_skipped" {
  description = "Configured AI Platform agents skipped (not provisioned in project yet)."
  value       = module.ai_platform_agents.skipped_service_agents
}

output "agent_engine_deploy_enabled" {
  value = var.deploy_agent_engine
}
