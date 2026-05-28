# -----------------------------------------------------------------------------
# Private Service Connect — consumer network attachment (Agent Engine PSC egress)
# https://cloud.google.com/vertex-ai/docs/general/vpc-psc-i-setup
# -----------------------------------------------------------------------------

resource "google_compute_subnetwork" "psc_attachment" {
  name          = var.psc_subnet_name
  project       = var.project_id
  region        = var.region
  network       = var.network_id
  ip_cidr_range = var.psc_subnet_range

  private_ip_google_access = true

  description = "Subnet for Private Service Connect network attachment (Agent Engine PSC interface)"
}

resource "google_compute_network_attachment" "agent_engine" {
  name                  = var.attachment_name
  project               = var.project_id
  region                = var.region
  connection_preference = var.connection_preference
  subnetworks           = [google_compute_subnetwork.psc_attachment.self_link]

  description = "PSC network attachment for Vertex AI Agent Engine"
}

# Agent Engine (PSC subnet) → SAP on-prem / RFC1918 host
resource "google_compute_firewall" "agent_engine_to_sap" {
  count = var.create_firewall ? 1 : 0

  name    = var.firewall_rule_name
  project = var.project_id
  network = var.network_name

  description = "Allow Agent Engine PSC traffic to SAP"

  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = var.firewall_ports
  }

  source_ranges      = [var.psc_subnet_range]
  destination_ranges = ["${var.psc_ip}/32"]

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

# PSC subnet → consumer workload subnet (e.g. explicit proxy VM)
resource "google_compute_firewall" "psc_to_consumer" {
  count = var.create_psc_to_consumer_firewall && var.consumer_subnet_range != null ? 1 : 0

  name    = var.psc_to_consumer_firewall_name
  project = var.project_id
  network = var.network_name

  description = "Allow PSC network attachment subnet to reach consumer workload subnet"

  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
  }

  allow {
    protocol = "udp"
  }

  allow {
    protocol = "icmp"
  }

  source_ranges      = [var.psc_subnet_range]
  destination_ranges = [var.consumer_subnet_range]

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

# -----------------------------------------------------------------------------
# Cloud Router + NAT — internet egress through consumer VPC (VPC-SC / proxy path)
# -----------------------------------------------------------------------------

resource "google_compute_router" "psc" {
  count = var.enable_cloud_nat ? 1 : 0

  name    = var.router_name
  project = var.project_id
  region  = var.region
  network = var.network_id
}

resource "google_compute_router_nat" "psc" {
  count = var.enable_cloud_nat ? 1 : 0

  name    = var.nat_name
  project = var.project_id
  region  = var.region
  router  = google_compute_router.psc[0].name

  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = var.nat_log_filter
  }
}

# -----------------------------------------------------------------------------
# Private DNS — consumer-side zone for Agent Engine DNS peering
# -----------------------------------------------------------------------------

resource "google_dns_managed_zone" "psc_private" {
  count = var.enable_private_dns ? 1 : 0

  name        = var.dns_zone_name
  project     = var.project_id
  dns_name    = var.dns_name
  description = "Private DNS for PSC consumer (Agent Engine DNS peering)"

  visibility = "private"

  private_visibility_config {
    networks {
      network_url = var.network_id
    }
  }
}

resource "google_dns_record_set" "psc_private" {
  for_each = var.enable_private_dns ? var.dns_record_sets : {}

  name         = "${each.key}.${var.dns_name}"
  managed_zone = google_dns_managed_zone.psc_private[0].name
  project      = var.project_id
  type         = each.value.type
  ttl          = each.value.ttl
  rrdatas      = each.value.rrdatas
}

# IAP tunnel to consumer VMs
resource "google_compute_firewall" "iap_ssh" {
  count = var.enable_iap_ssh_firewall && var.consumer_subnet_range != null ? 1 : 0

  name    = var.iap_ssh_firewall_name
  project = var.project_id
  network = var.network_name

  description = "Allow IAP TCP forwarding to consumer subnet"

  direction = "INGRESS"
  priority  = 1000

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges      = ["35.235.240.0/20"]
  destination_ranges = [var.consumer_subnet_range]
}

locals {
  network_attachment_id = "projects/${var.project_id}/regions/${var.region}/networkAttachments/${var.attachment_name}"
}
