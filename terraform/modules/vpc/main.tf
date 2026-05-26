resource "google_compute_network" "this" {
  count = var.vpc_mode == "create" ? 1 : 0

  project                 = var.project_id
  name                    = var.vpc_name
  auto_create_subnetworks = false
  routing_mode            = var.routing_mode

  delete_default_routes_on_create = var.delete_default_routes_on_create
}

data "google_compute_network" "existing" {
  count = var.vpc_mode == "existing" ? 1 : 0

  name    = var.vpc_name
  project = var.project_id
}

locals {
  network_id        = var.vpc_mode == "create" ? google_compute_network.this[0].id : data.google_compute_network.existing[0].id
  network_name      = var.vpc_mode == "create" ? google_compute_network.this[0].name : data.google_compute_network.existing[0].name
  network_self_link = var.vpc_mode == "create" ? google_compute_network.this[0].self_link : data.google_compute_network.existing[0].self_link
}

resource "google_compute_subnetwork" "consumer" {
  count = var.create_consumer_subnet ? 1 : 0

  name          = var.consumer_subnet_name
  project       = var.project_id
  region        = var.region
  network       = local.network_id
  ip_cidr_range = var.consumer_subnet_range

  private_ip_google_access = true
}
