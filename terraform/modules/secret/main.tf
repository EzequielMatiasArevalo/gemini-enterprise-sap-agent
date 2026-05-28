resource "google_secret_manager_secret" "credentials" {
  project   = var.project_id
  secret_id = var.secret_id

  replication {
    auto {}
  }
}
