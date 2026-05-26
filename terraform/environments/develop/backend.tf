# Configure the GCS backend after running bootstrap/setup_remote_state.sh.
# Example:
#   terraform init -backend-config=backend.gcs.tfbackend
terraform {
  backend "gcs" {}
}
