terraform {
  required_providers {
    google-beta = {
      source = "hashicorp/google-beta"
    }
  }
}

# Ensures the Vertex AI service agent exists before IAM bindings (fixes 403 on
# compute.networkAttachments.get during Agent Engine deploy with PSC).
resource "google_project_service_identity" "aiplatform" {
  provider = google-beta

  project = var.project_id
  service = "aiplatform.googleapis.com"
}

locals {
  primary_agent = google_project_service_identity.aiplatform.email

  additional_agents = [
    for suffix in var.additional_service_agent_suffixes :
    "service-${var.project_number}@${suffix}.iam.gserviceaccount.com"
  ]

  # Keys must be known at plan time — use static SA emails + roles (not service identity email).
  additional_bindings = merge([
    for sa in local.additional_agents : {
      for role in var.roles :
      "${sa}:${role}" => {
        member = "serviceAccount:${sa}"
        role   = role
      }
    }
  ]...)
}

resource "google_project_iam_member" "primary_aiplatform" {
  for_each = toset(var.roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_project_service_identity.aiplatform.email}"
}

resource "google_project_iam_member" "additional_aiplatform" {
  for_each = local.additional_bindings

  project = var.project_id
  role    = each.value.role
  member  = each.value.member
}
