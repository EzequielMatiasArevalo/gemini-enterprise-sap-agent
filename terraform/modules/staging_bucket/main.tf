locals {
  bucket_name = coalesce(var.bucket_name, "${var.project_id}_cloudbuild")
}

resource "google_storage_bucket" "staging" {
  name          = local.bucket_name
  project       = var.project_id
  location      = var.region
  force_destroy = var.force_destroy

  uniform_bucket_level_access = true

  versioning {
    enabled = false
  }
}
