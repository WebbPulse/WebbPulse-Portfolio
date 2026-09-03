variable "aws_region" {
  description = "AWS region to deploy resources into"
  type        = string
  default     = "us-west-2"
}

variable "db_instance_class" {
  description = "RDS instance type"
  type        = string
  default     = "db.t4g.micro"
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "webbpulse"
}

variable "db_username" {
  description = "PostgreSQL master username"
  type        = string
  default     = "webbpulse"
}

variable "environment" {
  description = "Deployment environment (production, staging)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["production", "staging"], var.environment)
    error_message = "environment must be 'production' or 'staging'"
  }
}

variable "staging_profile" {
  description = "How much of the stack this environment provisions. 'none' means the environment is switched off and must not be built. Set on the workspace by the WebbPulse-Organization workspace factory."
  type        = string
  default     = "full"

  validation {
    condition     = contains(["none", "reduced", "full"], var.staging_profile)
    error_message = "staging_profile must be one of 'none', 'reduced', or 'full'."
  }

  validation {
    condition     = var.staging_profile != "none"
    error_message = "Refusing to plan: staging_profile is 'none', so this environment is switched off and no resources should be created in it. To stand this environment up, change staging_profile to 'reduced' or 'full' on the workspace in WebbPulse-Organization/bootstrap/locals.tf."
  }
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID for webbpulse.com. Owned by the WebbPulse-Organization bootstrap workspace and delivered here as a workspace variable."
  type        = string
  default     = null

  validation {
    condition     = var.environment != "production" || var.route53_zone_id != null
    error_message = "route53_zone_id must be set when environment is 'production'. The webbpulse.com hosted zone is owned by the WebbPulse-Organization bootstrap workspace; set the workspace variable from WebbPulse-Organization/bootstrap/locals.tf."
  }
}

variable "route53_write_role_arn" {
  description = "IAM role ARN assumed to write records into the webbpulse.com hosted zone, which is owned by another account. Delivered here as a workspace variable. Empty means write with the run role directly."
  type        = string
  default     = ""
}

variable "legacy_stack_enabled" {
  description = "Keep the RDS + App Runner stack alive alongside the Lambda + DynamoDB stack while data is migrated. Only ever true in production; set to false after the DNS cutover to destroy the legacy resources."
  type        = bool
  default     = true
}

variable "api_dns_target" {
  description = "Which backend api.webbpulse.com resolves to. Flip to 'apigateway' after the data migration has been verified; 'apprunner' requires legacy_stack_enabled."
  type        = string
  default     = "apprunner"

  validation {
    condition     = contains(["apprunner", "apigateway"], var.api_dns_target)
    error_message = "api_dns_target must be 'apprunner' or 'apigateway'."
  }

  validation {
    condition     = var.api_dns_target != "apprunner" || var.legacy_stack_enabled
    error_message = "api_dns_target 'apprunner' requires legacy_stack_enabled = true; flip DNS to 'apigateway' before disabling the legacy stack."
  }
}
