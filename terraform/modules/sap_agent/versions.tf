terraform {
  required_providers {
    google-beta = {
      source = "hashicorp/google-beta"
    }
    time = {
      source  = "hashicorp/time"
      version = ">= 0.9"
    }
  }
}
