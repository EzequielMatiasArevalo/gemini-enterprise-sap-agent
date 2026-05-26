output "deploy_triggered" {
  description = "Whether the deploy null_resource was created."
  value       = var.enabled
}

output "deploy_revision" {
  description = "Current deploy revision trigger."
  value       = var.deploy_revision
}
