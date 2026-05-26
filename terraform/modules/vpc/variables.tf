variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "Region for regional subnets."
  type        = string
}

variable "vpc_mode" {
  description = "VPC strategy: create a new network or use an existing one."
  type        = string
  default     = "existing"

  validation {
    condition     = contains(["create", "existing"], var.vpc_mode)
    error_message = "vpc_mode must be \"create\" or \"existing\"."
  }
}

variable "vpc_name" {
  description = "VPC network name. Used as the name when creating, or to look up when reusing."
  type        = string
  default     = "sap-agent-vpc"
}

variable "routing_mode" {
  description = "VPC routing mode when creating a network (REGIONAL or GLOBAL)."
  type        = string
  default     = "REGIONAL"
}

variable "delete_default_routes_on_create" {
  description = "Delete default internet route when creating the VPC."
  type        = bool
  default     = false
}

variable "create_consumer_subnet" {
  description = "Create a workload subnet (e.g. for proxy VM) in the VPC."
  type        = bool
  default     = false
}

variable "consumer_subnet_name" {
  description = "Workload subnet name."
  type        = string
  default     = "consumer-subnet"
}

variable "consumer_subnet_range" {
  description = "CIDR for the workload subnet."
  type        = string
  default     = "10.10.10.0/28"
}
