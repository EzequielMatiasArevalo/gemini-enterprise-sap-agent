output "email" {
  description = "Service account email."
  value       = google_service_account.agent_engine.email
}

output "name" {
  description = "Fully qualified service account resource name."
  value       = google_service_account.agent_engine.name
}

output "member" {
  description = "IAM member string for the service account."
  value       = "serviceAccount:${google_service_account.agent_engine.email}"
}
