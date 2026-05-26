variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "apis" {
  description = "List of GCP API service names to enable."
  type        = list(string)
  default = [
    "compute.googleapis.com",
    "aiplatform.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "dns.googleapis.com",
    "servicenetworking.googleapis.com",
  ]
}

variable "disable_on_destroy" {
  description = "Whether to disable APIs when the module is destroyed."
  type        = bool
  default     = false
}
