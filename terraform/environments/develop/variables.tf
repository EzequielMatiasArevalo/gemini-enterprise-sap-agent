variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (used in state prefix and labels)."
  type        = string
  default     = "dev"
}

variable "repo_root" {
  description = "Repository root path (for Agent Engine deploy script)."
  type        = string
  default     = null
}

# --- VPC ---
variable "vpc_mode" {
  description = "create = new VPC; existing = reuse by name."
  type        = string
  default     = "existing"
}

variable "vpc_name" {
  description = "VPC network name."
  type        = string
  default     = "sap-cal-default-network"
}

variable "create_consumer_subnet" {
  description = "Workload subnet for proxy VM (optional)."
  type        = bool
  default     = false
}

variable "consumer_subnet_range" {
  type    = string
  default = "10.10.10.0/28"
}

# --- Private Service Connect ---
variable "enable_psc" {
  description = "Deploy PSC consumer infrastructure."
  type        = bool
  default     = true
}

variable "sap_ip" {
  description = "SAP host IP for PSC firewall (RFC1918 on-prem)."
  type        = string
  default     = "10.142.0.5"
}

variable "enable_psc_nat" {
  description = "Cloud NAT for internet egress via consumer VPC."
  type        = bool
  default     = false
}

variable "enable_psc_private_dns" {
  description = "Private DNS zone for PSC DNS peering."
  type        = bool
  default     = false
}

variable "psc_dns_record_sets" {
  description = "DNS A records (hostname prefix → IP), e.g. proxy-vm = 10.10.10.2"
  type = map(object({
    type    = string
    ttl     = number
    rrdatas = list(string)
  }))
  default = {}
}

variable "enable_psc_to_consumer_firewall" {
  type    = bool
  default = false
}

variable "enable_iap_ssh_firewall" {
  type    = bool
  default = false
}

# --- Agent Engine ---
variable "deploy_agent_engine" {
  description = "Deploy Agent Engine via null_resource (requires sap-credentials secret version)."
  type        = bool
  default     = false
}

variable "sap_credentials_secrets" {
  description = ""
  default = "sap-credentials-example"
}

variable "agent_engine_resource_name" {
  description = "Existing Agent Engine resource to update (optional)."
  type        = string
  default     = null
}

variable "agent_deploy_revision" {
  description = "Bump to trigger Agent Engine redeploy."
  type        = string
  default     = "1"
}

variable "aiplatform_iam_wait_seconds" {
  description = "Wait for Vertex AI service agent IAM propagation before deploy."
  type        = number
  default     = 45
}


variable "agent_service_account" {
  description = ""
  default = "test-sa"
}

variable "staging_bucket_name" {
  description = ""
  default = "staging-bucket-sap"
}

variable "network_attachment_name" {
  description = ""
  default = "sap-network-attachment-ex"
}

variable "agent_module" {
  description = "Python module path of the agent package to deploy (passed to deploy script as --agent-module)."
  type        = string
  default     = "sap_abap_agent_v2"
}

variable "agent_engine_env_vars" {
  description = <<-EOT
    Additional non-secret env vars for the Agent Engine container.
    Merged on top of the auto-derived GOOGLE_CLOUD_PROJECT / _LOCATION /
    _BUCKET defaults and on top of deploy.env_vars from config.yaml.
    User-supplied keys win.
  EOT
  type        = map(string)
  default     = {}
}
