locals {
  # KEY=value,KEY=value (consumed by the deploy script's --env-vars flag).
  extra_env_vars_cli = join(",", [for k, v in var.extra_env_vars : "${k}=${v}"])

  optional_cli_flags = compact([
    var.agent_engine_resource_name != null ? "--update \"${var.agent_engine_resource_name}\"" : null,
    var.agent_module != null ? "--agent-module \"${var.agent_module}\"" : null,
    var.service_account != null ? "--service-account \"${var.service_account}\"" : null,
    var.network_attachment != null ? "--network-attachment \"${var.network_attachment}\"" : null,
    var.credentials_secret != null ? "--credentials \"${var.credentials_secret}\"" : null,
    length(var.extra_env_vars) > 0 ? "--env-vars \"${local.extra_env_vars_cli}\"" : null,
  ])

  deploy_cli_flags = join(" \\\n        ", local.optional_cli_flags)
}

# Vertex AI Agent Engine (Reasoning Engine) is not yet modeled in the Google provider.
# Deploy via deploy_agent_engine.py. All deploy-time agent settings
# (display_name, resource_limits, requirements, extra_packages, env_vars)
# live in ``<agent_module>/config.yaml`` and are loaded by the script.
resource "null_resource" "deploy_agent_engine" {
  count = var.enabled ? 1 : 0

  triggers = {
    project_id                 = var.project_id
    region                     = var.region
    staging_bucket_url         = var.staging_bucket_url
    agent_engine_resource_name = var.agent_engine_resource_name != null ? var.agent_engine_resource_name : ""
    agent_module               = var.agent_module != null ? var.agent_module : ""
    deploy_revision            = var.deploy_revision
    service_account            = var.service_account != null ? var.service_account : ""
    network_attachment         = var.network_attachment != null ? var.network_attachment : ""
    credentials_secret         = var.credentials_secret != null ? var.credentials_secret : ""
    extra_env_vars             = jsonencode(var.extra_env_vars)
  }

  provisioner "local-exec" {
    working_dir = var.repo_root
    command     = <<-EOT
      set -euo pipefail
      ${var.python_interpreter} scripts/deploy_agent_engine.py \
        --project "${var.project_id}" \
        --region "${var.region}" \
        --staging-bucket "${var.staging_bucket_url}" \
        ${local.deploy_cli_flags}
    EOT

    interpreter = ["/bin/bash", "-c"]
  }
}
