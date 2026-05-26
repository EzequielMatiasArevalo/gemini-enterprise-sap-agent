variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "account_id" {
  description = "Service account ID (short name)."
  type        = string
  default     = "agent-engine-sa"
}

variable "display_name" {
  description = "Display name for the service account."
  type        = string
  default     = "SAP Agent Engine Service Account"
}

variable "description" {
  description = "Description for the service account."
  type        = string
  default     = "Service account for SAP Agent deployed on Vertex AI Agent Engine"
}

variable "roles" {
  description = "IAM roles to grant the service account at project level."
  type        = list(string)
  default = [
    "roles/aiplatform.user",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectViewer",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/serviceusage.serviceUsageConsumer",
  ]
}
