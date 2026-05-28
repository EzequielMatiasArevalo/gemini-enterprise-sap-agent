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
  description = "Environment label (dev, staging, prod) for naming and documentation."
  type        = string
  default     = "dev"
}

variable "repo_root" {
  description = "Absolute path to repository root (required when deploy_agent_engine is true)."
  type        = string
  default     = null
}

# --- APIs ---
variable "apis" {
  description = "GCP APIs to enable. Override to extend or trim the default set."
  type        = list(string)
  default     = null
}

# --- Service account ---
variable "service_account_id" {
  description = "Agent Engine service account short ID."
  type        = string
  default     = "agent-engine-sa"
}

variable "service_account_roles" {
  description = "IAM roles for the Agent Engine service account."
  type        = list(string)
  default     = null
}

# --- Staging bucket ---
variable "staging_bucket_name" {
  description = "Override staging bucket name."
  type        = string
  default     = null
}

# --- Secret ---
variable "secret_id" {
  description = "Secret Manager secret ID for SAP credentials."
  type        = string
  default     = "sap-credentials"
}

# --- VPC ---
variable "vpc_mode" {
  description = "VPC strategy: \"create\" a new network or \"existing\" (reuse by name)."
  type        = string
  default     = "existing"

  validation {
    condition     = contains(["create", "existing"], var.vpc_mode)
    error_message = "vpc_mode must be \"create\" or \"existing\"."
  }
}

variable "vpc_name" {
  description = "VPC name (created when vpc_mode=create, or looked up when existing)."
  type        = string
  default     = "sap-cal-default-network"
}

variable "create_consumer_subnet" {
  description = "Create a workload subnet in the VPC (recommended when vpc_mode=create)."
  type        = bool
  default     = false
}

variable "consumer_subnet_name" {
  type    = string
  default = "consumer-subnet"
}

variable "consumer_subnet_range" {
  type    = string
  default = "10.10.10.0/28"
}

# --- Private Service Connect ---
variable "enable_psc" {
  description = "Deploy Private Service Connect consumer infrastructure (subnet, network attachment, firewalls)."
  type        = bool
  default     = true
}

variable "psc_subnet_name" {
  type    = string
  default = "psc-attachment-subnet"
}

variable "psc_subnet_range" {
  type    = string
  default = "192.168.10.0/28"
}

variable "network_attachment_name" {
  type    = string
  default = "agent-engine-attachment"
}

variable "psc_ip" {
  type    = string
  default = "10.142.0.5"
}

variable "enable_psc_nat" {
  description = "Cloud Router + Cloud NAT for internet egress via consumer VPC (explicit proxy path)."
  type        = bool
  default     = false
}

variable "enable_psc_private_dns" {
  description = "Private Cloud DNS zone on the VPC for Agent Engine DNS peering."
  type        = bool
  default     = false
}

variable "psc_dns_zone_name" {
  type    = string
  default = "psc-private-dns"
}

variable "psc_dns_name" {
  description = "Private zone DNS name (trailing dot required), e.g. sap.internal."
  type        = string
  default     = "sap.internal."
}

variable "psc_dns_record_sets" {
  description = "DNS records in the private zone (map key = record hostname prefix)."
  type = map(object({
    type    = string
    ttl     = number
    rrdatas = list(string)
  }))
  default = {}
}

variable "enable_psc_to_consumer_firewall" {
  description = "Firewall: PSC subnet → consumer workload subnet (requires create_consumer_subnet)."
  type        = bool
  default     = false
}

variable "enable_iap_ssh_firewall" {
  description = "Firewall: IAP → consumer subnet SSH (for proxy VM administration)."
  type        = bool
  default     = false
}

variable "aiplatform_iam_wait_seconds" {
  description = "Seconds to wait after granting Vertex AI service agent IAM before deploy."
  type        = number
  default     = 90
}

# --- Agent Engine deploy (null_resource) ---
variable "deploy_agent_engine" {
  description = "Run deploy_agent_engine.py via null_resource after infrastructure is ready."
  type        = bool
  default     = false
}

variable "agent_engine_resource_name" {
  description = "Update existing Agent Engine resource instead of create."
  type        = string
  default     = null
}

variable "agent_deploy_revision" {
  description = "Bump to force Agent Engine redeploy."
  type        = string
  default     = "1"
}

variable "python_interpreter" {
  type    = string
  default = "python3"
}

variable "agent_module" {
  description = "Python module path of the agent package to deploy (passed to deploy script as --agent-module). Example: 'abap_agent_v2' or 'my_other_agent'."
  type        = string
}

variable "agent_engine_env_vars" {
  description = <<-EOT
    Additional non-secret env vars to ship to the Agent Engine container.
    Merged on top of the auto-derived GOOGLE_CLOUD_PROJECT / _LOCATION /
    _BUCKET defaults and on top of deploy.env_vars from config.yaml.
    User-supplied keys win.
  EOT
  type        = map(string)
  default     = {}
}
