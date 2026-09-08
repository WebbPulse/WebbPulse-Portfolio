variable "aws_region" {
  description = "AWS region to deploy resources into"
  type        = string
  default     = "us-west-2"
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
  description = "Route53 hosted zone ID of the parent zone (webbpulse.com), owned by another account and delivered here as a workspace variable. Production writes its workload records into it; staging writes only the NS delegation for its child zone into it."
  type        = string
  default     = null

  validation {
    condition     = var.environment != "production" || var.route53_zone_id != null
    error_message = "route53_zone_id must be set when environment is 'production'. The webbpulse.com hosted zone is owned by the WebbPulse-Organization bootstrap workspace; set the workspace variable from WebbPulse-Organization/bootstrap/locals.tf."
  }
}

variable "route53_write_role_arn" {
  description = "IAM role ARN in the management account assumed to write into the parent zone (route53_zone_id). In production it is the writer role for the workload records; in staging it is the delegation role allowed only the NS record for the child zone. Delivered here as a workspace variable. Empty means write with the run role directly."
  type        = string
  default     = ""

  validation {
    condition     = var.environment != "staging" || var.staging_profile != "full" || var.route53_write_role_arn != ""
    error_message = "route53_write_role_arn must be set when environment is 'staging' and staging_profile is 'full': the staging child zone is delegated from the parent zone through that role."
  }
}

variable "staging_access_gate" {
  description = "Put the staging site and API behind the staging-access-gate module (Cognito sign-in, CloudFront signed cookies, origin-verified API). WebbPulse-Platform sets this on staging workspaces only; production never receives it and keeps the default of false."
  type        = bool
  default     = false
}

variable "staging_access_users" {
  description = "Email addresses allowed through the staging access gate. Each becomes an invited Cognito user. WebbPulse-Platform sets this on staging workspaces only; production never receives it."
  type        = list(string)
  default     = []
}

variable "admin_username" {
  description = "Username of the seeded admin user, delivered into the webbpulse-<env>/app secret. Set as a sensitive workspace variable in HCP Terraform; there is no default, so a workspace that has not been given one fails to plan rather than seeding a guessable account."
  type        = string
  sensitive   = true
}

variable "admin_password" {
  description = "Password of the seeded admin user, delivered into the webbpulse-<env>/app secret. Set as a sensitive workspace variable in HCP Terraform; there is no default, so a workspace that has not been given one fails to plan rather than seeding a guessable account."
  type        = string
  sensitive   = true
}

variable "admin_email" {
  description = "Email address of the seeded admin user, delivered into the webbpulse-<env>/app secret. Set as a sensitive workspace variable in HCP Terraform; there is no default, so a workspace that has not been given one fails to plan rather than seeding a guessable account."
  type        = string
  sensitive   = true
}

variable "manage_spans_log_group" {
  description = "Adopt the aws/spans log group into state and apply the platform's 7 day retention to it. Leave false until Transaction Search has applied in this environment and X-Ray has written its first span: the group cannot be created by Terraform (CloudWatch reserves the aws/ prefix), so an import of it before it exists fails the plan. Set to true on the workspace and apply again once the group is there."
  type        = bool
  default     = false
}
