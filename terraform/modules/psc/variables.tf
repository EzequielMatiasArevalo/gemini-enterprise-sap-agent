variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for PSC resources."
  type        = string
}

variable "network_id" {
  description = "VPC network ID (from vpc module)."
  type        = string
}

variable "network_name" {
  description = "VPC network name (for firewall resources)."
  type        = string
}

variable "psc_subnet_name" {
  description = "PSC network attachment subnet name."
  type        = string
  default     = "psc-attachment-subnet"
}

variable "psc_subnet_range" {
  description = "CIDR range for the PSC network attachment subnet."
  type        = string
  default     = "192.168.10.0/28"
}

variable "attachment_name" {
  description = "Private Service Connect network attachment name."
  type        = string
  default     = "agent-engine-attachment"
}

variable "connection_preference" {
  description = "Network attachment connection preference (ACCEPT_AUTOMATIC or ACCEPT_MANUAL)."
  type        = string
  default     = "ACCEPT_AUTOMATIC"
}

# --- SAP on-prem / RFC1918 target ---
variable "sap_ip" {
  description = "SAP target IP for direct PSC firewall destination."
  type        = string
  default     = "10.142.0.5"
}

variable "create_sap_firewall" {
  description = "Allow PSC subnet ingress to SAP IP (on-prem RFC1918)."
  type        = bool
  default     = true
}

variable "firewall_rule_name" {
  description = "Firewall rule name for Agent Engine PSC to SAP."
  type        = string
  default     = "allow-agent-engine-to-sap"
}

variable "firewall_ports" {
  description = "TCP ports allowed from PSC subnet to SAP."
  type        = list(string)
  default     = ["44300", "8000", "443", "80"]
}

# --- Consumer workload subnet (proxy VM) ---
variable "consumer_subnet_range" {
  description = "CIDR of consumer workload subnet for PSC-to-proxy firewall (null to skip)."
  type        = string
  default     = null
}

variable "create_psc_to_consumer_firewall" {
  description = "Allow PSC attachment subnet to reach consumer workload subnet."
  type        = bool
  default     = false
}

variable "psc_to_consumer_firewall_name" {
  type    = string
  default = "allow-psc-to-consumer"
}

# --- Cloud NAT (internet egress via consumer VPC) ---
variable "enable_cloud_nat" {
  description = "Create Cloud Router and Cloud NAT for consumer VPC internet egress."
  type        = bool
  default     = false
}

variable "router_name" {
  type    = string
  default = "psc-cloud-router"
}

variable "nat_name" {
  type    = string
  default = "psc-cloud-nat"
}

variable "nat_log_filter" {
  description = "NAT logging filter (ERRORS_ONLY, TRANSLATIONS_ONLY, ALL)."
  type        = string
  default     = "ALL"
}

# --- Private DNS (PSC explicit proxy / DNS peering consumer side) ---
variable "enable_private_dns" {
  description = "Create a private Cloud DNS zone attached to the VPC for PSC DNS peering."
  type        = bool
  default     = false
}

variable "dns_zone_name" {
  type    = string
  default = "psc-private-dns"
}

variable "dns_name" {
  description = "Private DNS zone DNS name (must end with a dot), e.g. sap.internal."
  type        = string
  default     = "sap.internal."
}

variable "dns_record_sets" {
  description = "DNS A/AAAA records in the private zone (name relative to dns_name, without trailing dot)."
  type = map(object({
    type    = string
    ttl     = number
    rrdatas = list(string)
  }))
  default = {}
}

# --- IAP SSH to consumer VMs ---
variable "enable_iap_ssh_firewall" {
  description = "Allow IAP TCP forwarding (35.235.240.0/20) to consumer subnet on port 22."
  type        = bool
  default     = false
}

variable "iap_ssh_firewall_name" {
  type    = string
  default = "allow-iap-ssh-consumer"
}
