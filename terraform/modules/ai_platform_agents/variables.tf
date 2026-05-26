variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "project_number" {
  description = "GCP project number (for optional additional managed service agents)."
  type        = string
}

variable "roles" {
  description = "IAM roles for the Vertex AI service agent (PSC network attachment access)."
  type        = list(string)
  default = [
    "roles/serviceusage.serviceUsageConsumer",
    "roles/compute.networkAdmin",
    "roles/compute.viewer",
    "roles/dns.peer",
  ]
}

variable "additional_service_agent_suffixes" {
  description = <<-EOT
    Optional extra Vertex AI service agents (re, cc). Only list suffixes for agents that
    already exist in the project, or apply will fail.
  EOT
  type    = list(string)
  default = []
}
