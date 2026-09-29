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
  description = "How much of the stack this environment provisions. 'none' switches the environment off."
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
  description = "Route53 hosted zone ID of the parent zone (webbpulse.com), owned by another account. Production writes workload records into it; staging writes only its child zone NS delegation."
  type        = string
  default     = null

  validation {
    condition     = var.environment != "production" || var.route53_zone_id != null
    error_message = "route53_zone_id must be set when environment is 'production'. The webbpulse.com hosted zone is owned by the WebbPulse-Organization bootstrap workspace; set the workspace variable from WebbPulse-Organization/bootstrap/locals.tf."
  }
}

variable "route53_write_role_arn" {
  description = "IAM role ARN in the management account assumed to write into the parent zone. Empty means write with the run role directly."
  type        = string
  default     = ""

  validation {
    condition     = var.environment != "staging" || var.staging_profile != "full" || var.route53_write_role_arn != ""
    error_message = "route53_write_role_arn must be set when environment is 'staging' and staging_profile is 'full': the staging child zone is delegated from the parent zone through that role."
  }
}

variable "route53_read_role_arn" {
  description = "Read-only counterpart of route53_write_role_arn, assumed instead of it during plans on the WebbPulse control plane. Pushed by WebbPulse-Platform next to the writer."
  type        = string
  default     = ""

  validation {
    condition     = var.route53_write_role_arn == "" || var.route53_read_role_arn != ""
    error_message = "route53_read_role_arn must be set whenever route53_write_role_arn is: plans on the WebbPulse control plane assume the reader. WebbPulse-Platform pushes both to the workspace."
  }
}

variable "webbpulse_run_phase" {
  description = "Run phase the WebbPulse control plane exports as TF_VAR_webbpulse_run_phase: plan or apply. Plans assume route53_read_role_arn and applies route53_write_role_arn. Ephemeral so a saved plan never carries plan into its apply, and defaulted to apply so HCP Terraform, which never sets it, keeps the writer."
  type        = string
  default     = "apply"
  ephemeral   = true

  validation {
    condition     = contains(["plan", "apply"], var.webbpulse_run_phase)
    error_message = "webbpulse_run_phase must be plan or apply."
  }
}

variable "staging_access_gate" {
  description = "Put the staging site and API behind the staging-access-gate module. Staging only; production keeps the default of false."
  type        = bool
  default     = false
}

variable "staging_access_users" {
  description = "Email addresses allowed through the staging access gate, each invited as a Cognito user"
  type        = list(string)
  default     = []
}

variable "manage_spans_log_group" {
  description = "Adopt the aws/spans log group into state and apply the platform's 7 day retention. Leave false until X-Ray has created the group, since Terraform cannot create it."
  type        = bool
  default     = false
}

variable "identity_jwt_mode" {
  description = "Which mechanism enforces identity access tokens at the gateway: the staging gate's Lambda authorizer (gate), API Gateway's own JWT authorizer (native), or nothing (off)."

  type    = string
  default = "off"

  validation {
    condition     = contains(["native", "gate", "off"], var.identity_jwt_mode)
    error_message = "identity_jwt_mode must be one of native, gate or off."
  }

  validation {
    condition     = var.identity_jwt_mode != "native" || var.environment != "staging"
    error_message = "identity_jwt_mode must not be native in staging. Every route there carries the staging access gate's REQUEST authorizer and a route takes exactly one authorizer, so a native JWT authorizer has no slot to occupy. Use gate, which moves the same check into the gate's own Lambda."
  }
}

variable "domain_jwt_enforced" {
  description = "Whether the /api/v1 admin route keys additionally require an identity access token at the gateway. The keys exist either way; this only marks them as enforced."

  type    = bool
  default = false
}
