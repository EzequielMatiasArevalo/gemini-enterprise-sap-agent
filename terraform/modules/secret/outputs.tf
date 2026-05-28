output "secret_id" {
  description = "Secret ID."
  value       = google_secret_manager_secret.credentials.secret_id
}

output "secret_name" {
  description = "Full secret resource name."
  value       = google_secret_manager_secret.credentials.name
}
