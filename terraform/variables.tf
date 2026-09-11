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

variable "identity_jwt_mode" {
  description = <<-EOT
    How the gateway enforces the identity module's access tokens on the routes that need an
    authenticated caller. The routes themselves are marked once, with require_identity_jwt in
    terraform/apigateway.tf; this variable only picks which of the two mechanisms carries out the
    check, because an HTTP API route takes exactly one authorizer and which one is free depends on
    whether the staging access gate is in front of the API.

      "gate"    The staging access gate's own Lambda authorizer does both checks: the signed gate
                cookie as before, then a valid Bearer access token on the marked routes. This is
                what a gated staging environment has to use, because the gate already occupies the
                route's one authorizer slot. module.api.identity_jwt stays null and no route moves.

      "native"  API Gateway's own JWT authorizer verifies the token: the RS256 signature against
                the issuer's JWKS, then iss, aud, exp and nbf, with nothing of ours on the request
                path. This is the ungated shape, which is what production is. The marked routes
                become authorization_type JWT and are replaced, because the platform module keeps
                them in a separate resource so the .well-known routes can exist before the
                authorizer and the protected routes after it.

      "off"     Nothing is enforced at the gateway. The applications still verify the token
                themselves, which they do in every mode: this is an extra gate in front of them,
                never a replacement for their own check.

    The default is "off" and PRODUCTION KEEPS IT for now. "native" creates an authorizer whose
    CreateAuthorizer call synchronously fetches <issuer>/.well-known/openid-configuration from
    outside AWS, so it fails unless the identity function is already deployed and already serving
    those two documents at the production API host. The identity stack has not been promoted to
    production yet, so turning this on there before that promotion fails the apply rather than
    leaving anything open. Set it to "native" on the production workspace in the apply that follows
    the promotion, not before.
  EOT

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
