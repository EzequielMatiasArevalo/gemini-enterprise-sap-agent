variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCS bucket location."
  type        = string
}

variable "bucket_name" {
  description = "Staging bucket name. Defaults to {project_id}_cloudbuild when null."
  type        = string
  default     = null
}

variable "force_destroy" {
  description = "Allow Terraform to delete bucket even if it contains objects."
  type        = bool
  default     = false
}
