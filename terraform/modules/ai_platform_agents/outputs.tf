output "primary_service_agent" {
  description = "Vertex AI service agent email (from google_project_service_identity)."
  value       = google_project_service_identity.aiplatform.email
}

output "configured_service_agents" {
  description = "Primary + configured additional service agent emails."
  value       = concat([google_project_service_identity.aiplatform.email], local.additional_agents)
}

output "bound_service_agents" {
  description = "Service agents that received IAM bindings."
  value       = concat([google_project_service_identity.aiplatform.email], local.additional_agents)
}

output "skipped_service_agents" {
  description = "Reserved for compatibility; additional agents are not probed at plan time."
  value       = []
}
