variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "secret_id" {
  description = "Secret Manager secret ID for SAP credentials."
  type        = string
  default     = "sap-credentials"
}
