output "vpc_mode" {
  description = "Whether the VPC was created or reused."
  value       = var.vpc_mode
}

output "network_id" {
  description = "VPC network ID."
  value       = local.network_id
}

output "network_name" {
  description = "VPC network name."
  value       = local.network_name
}

output "network_self_link" {
  description = "VPC network self link."
  value       = local.network_self_link
}

output "consumer_subnet_name" {
  description = "Workload subnet name (null if not created)."
  value       = try(google_compute_subnetwork.consumer[0].name, null)
}

output "consumer_subnet_range" {
  description = "Workload subnet CIDR (null if not created)."
  value       = var.create_consumer_subnet ? var.consumer_subnet_range : null
}

output "consumer_subnet_self_link" {
  description = "Workload subnet self link (null if not created)."
  value       = try(google_compute_subnetwork.consumer[0].self_link, null)
}
