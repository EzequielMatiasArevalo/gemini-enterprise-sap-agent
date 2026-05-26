variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for Agent Engine."
  type        = string
}

variable "repo_root" {
  description = "Absolute path to the repository root (for deploy script)."
  type        = string
}

variable "staging_bucket_url" {
  description = "GCS staging bucket URL (gs://bucket-name)."
  type        = string
}

variable "python_interpreter" {
  description = "Python executable used to run the deploy script."
  type        = string
  default     = "python3"
}

variable "agent_engine_resource_name" {
  description = "If set, update this Agent Engine instead of creating a new one."
  type        = string
  default     = null
}

variable "deploy_revision" {
  description = "Bump this value to force re-running the deploy provisioner."
  type        = string
  default     = "1"
}

variable "enabled" {
  description = "Whether to run the Agent Engine deploy provisioner."
  type        = bool
  default     = false
}

variable "service_account" {
  description = "Agent Engine runtime service account email."
  type        = string
  default     = null
}

variable "network_attachment" {
  description = "PSC network attachment resource ID for psc_interface_config."
  type        = string
  default     = null
}

variable "sap_credentials_secret" {
  description = "Secret Manager version resource name for SAP credentials."
  type        = string
  default     = null
}

variable "agent_module" {
  description = <<-EOT
    Python module path of the agent package to deploy (passed to the deploy
    script as --agent-module). The package must expose:
      * an ``agent`` submodule with a root agent attribute, and
      * a ``config.yaml`` file holding deploy-time settings
        (display_name, resource_limits, requirements, extra_packages, env_vars).
  EOT
  type        = string
  default     = "sap_abap_agent_v2"
}

variable "extra_env_vars" {
  description = <<-EOT
    Non-secret environment variables to ship to the Agent Engine container.
    Passed to the deploy script as ``--env-vars KEY=value,...`` and merged
    on top of ``deploy.env_vars`` from the agent's config.yaml.
    Use this for environment-bound values (project ID, region, staging
    bucket, etc.) that must not be hardcoded inside the agent package.
  EOT
  type        = map(string)
  default     = {}
}
