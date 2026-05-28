output "psc_subnet_name" {
  description = "PSC network attachment subnet name."
  value       = google_compute_subnetwork.psc_attachment.name
}

output "psc_subnet_range" {
  description = "PSC network attachment subnet CIDR."
  value       = var.psc_subnet_range
}

output "psc_subnet_self_link" {
  value = google_compute_subnetwork.psc_attachment.self_link
}

output "network_attachment_name" {
  description = "PSC network attachment name."
  value       = google_compute_network_attachment.agent_engine.name
}

output "network_attachment_id" {
  description = "Full network attachment resource ID for Agent Engine psc_interface_config."
  value       = local.network_attachment_id
}

output "network_attachment_self_link" {
  value = google_compute_network_attachment.agent_engine.self_link
}

output "firewall_name" {
  value = try(google_compute_firewall.agent_engine_to_sap[0].name, null)
}

output "cloud_router_name" {
  value = try(google_compute_router.psc[0].name, null)
}

output "cloud_nat_name" {
  value = try(google_compute_router_nat.psc[0].name, null)
}

output "private_dns_zone_name" {
  value = try(google_dns_managed_zone.psc_private[0].name, null)
}

output "private_dns_zone_dns_name" {
  value = try(google_dns_managed_zone.psc_private[0].dns_name, null)
}
