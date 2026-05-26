output "name" {
  description = "Bucket name."
  value       = google_storage_bucket.staging.name
}

output "url" {
  description = "GCS URL for the staging bucket."
  value       = "gs://${google_storage_bucket.staging.name}"
}
