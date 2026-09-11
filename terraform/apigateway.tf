locals {
  routed_lambda_domains = ["public", "resume", "content", "identity"]

  resume_collections = [
    "projects",
    "experience",
    "skills",
    "education",
    "certifications",
  ]

  content_prefixes = [
    "posts",
    "site-content",
  ]

  domain_identity_jwt_route_paths = {
    content = [
      "GET /api/v1/posts/admin",
      "POST /api/v1/posts/admin",
      "PUT /api/v1/posts/admin/{post_id}",
      "DELETE /api/v1/posts/admin/{post_id}",
      "POST /api/v1/posts/admin/{post_id}/publish",
      "POST /api/v1/posts/categories",
      "PUT /api/v1/posts/categories/{category_id}",
      "DELETE /api/v1/posts/categories/{category_id}",
      "PUT /api/v1/site-content",
    ]

    resume = [
      "POST /api/v1/certifications",
      "PUT /api/v1/certifications/{item_id}",
      "DELETE /api/v1/certifications/{item_id}",
      "POST /api/v1/education",
      "PUT /api/v1/education/{item_id}",
      "DELETE /api/v1/education/{item_id}",
      "POST /api/v1/experience",
      "PUT /api/v1/experience/{item_id}",
      "DELETE /api/v1/experience/{item_id}",
      "POST /api/v1/projects",
      "PUT /api/v1/projects/{item_id}",
      "DELETE /api/v1/projects/{item_id}",
      "POST /api/v1/skills",
      "PUT /api/v1/skills/{item_id}",
      "DELETE /api/v1/skills/{item_id}",
    ]
  }

  domain_identity_jwt_route_keys = merge([
    for domain, keys in local.domain_identity_jwt_route_paths : {
      for key in keys : key => {
        integration          = domain
        require_identity_jwt = var.domain_jwt_enforced
      }
    }
  ]...)
}

module "api" {
  source = "app.terraform.io/WebbPulse/platform-modules/aws//modules/http-api"

  version = "~> 2.9"

  name = "${local.prefix}-api"

  integrations = {
    for name in local.routed_lambda_domains : name => {
      lambda_function_name = module.lambda_domain[name].function_name
      lambda_invoke_arn    = module.lambda_domain[name].invoke_arn
    }
  }

  default_integration = null

  routes = merge(
    {
      "GET /health"      = { integration = "public" }
      "GET /"            = { integration = "public" }
      "GET /sitemap.xml" = { integration = "public" }
      "GET /robots.txt"  = { integration = "public" }
    },

    merge([
      for collection in local.resume_collections : {
        "ANY /api/v1/${collection}"          = { integration = "resume" }
        "ANY /api/v1/${collection}/{proxy+}" = { integration = "resume" }
      }
    ]...),

    merge([
      for prefix in local.content_prefixes : {
        "ANY /api/v1/${prefix}"          = { integration = "content" }
        "ANY /api/v1/${prefix}/{proxy+}" = { integration = "content" }
      }
    ]...),

    {
      "ANY /api/v1/admin"          = { integration = "identity" }
      "ANY /api/v1/admin/{proxy+}" = { integration = "identity" }
    },

    {
      "GET /api/auth/.well-known/jwks.json" = {
        integration        = "identity"
        authorization_type = "NONE"
      }
      "GET /api/auth/.well-known/openid-configuration" = {
        integration        = "identity"
        authorization_type = "NONE"
      }
    },

    {
      "GET /api/auth/health" = { integration = "identity" }
    },

    {
      "POST /api/auth/register" = { integration = "identity" }
      "POST /api/auth/login"    = { integration = "identity" }
      "POST /api/auth/password" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/refresh" = { integration = "identity" }
      "POST /api/auth/logout"  = { integration = "identity" }
      "POST /api/auth/logout-all" = {
        integration          = "identity"
        require_identity_jwt = true
      }
    },

    {
      "POST /api/auth/verify-email"         = { integration = "identity" }
      "POST /api/auth/verify-email/confirm" = { integration = "identity" }
      "POST /api/auth/reset"                = { integration = "identity" }
      "POST /api/auth/reset/confirm"        = { integration = "identity" }
    },

    {
      "POST /api/auth/login/totp" = { integration = "identity" }
      "POST /api/auth/totp/enrol" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/totp/activate" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/totp/disable" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/recovery-codes" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/step-up" = {
        integration          = "identity"
        require_identity_jwt = true
      }
    },

    {
      "GET /api/auth/passkeys/availability" = { integration = "identity" }
      "POST /api/auth/passkeys/register/options" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/passkeys/register/verify" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "POST /api/auth/login/passkey/options" = { integration = "identity" }
      "POST /api/auth/login/passkey/verify"  = { integration = "identity" }
      "GET /api/auth/passkeys" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "PATCH /api/auth/passkeys/{credential_id}" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "DELETE /api/auth/passkeys/{credential_id}" = {
        integration          = "identity"
        require_identity_jwt = true
      }
    },

    {
      "GET /api/auth/oauth/providers"        = { integration = "identity" }
      "GET /api/auth/oauth/{provider}/start" = { integration = "identity" }
      "GET /api/auth/oauth/callback"         = { integration = "identity" }
      "POST /api/auth/oauth/{provider}/link" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "GET /api/auth/oauth/links" = {
        integration          = "identity"
        require_identity_jwt = true
      }
      "DELETE /api/auth/oauth/{provider}/link" = {
        integration          = "identity"
        require_identity_jwt = true
      }
    },

    local.domain_identity_jwt_route_keys,
  )

  throttling_burst_limit = 200
  throttling_rate_limit  = 100

  access_log_retention_days = 7

  lambda_permission_statement_id = "AllowAPIGatewayInvoke"

  access_log_format = {
    requestId               = "$context.requestId"
    ip                      = "$context.identity.sourceIp"
    requestTime             = "$context.requestTime"
    httpMethod              = "$context.httpMethod"
    routeKey                = "$context.routeKey"
    path                    = "$context.path"
    status                  = "$context.status"
    responseLength          = "$context.responseLength"
    integrationErrorMessage = "$context.integrationErrorMessage"
    integrationLatency      = "$context.integrationLatency"
  }

  cors_configuration = {
    allow_origins = split(",", local.cors_origins)
    allow_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_headers = [
      "Accept",
      "Accept-Language",
      "Authorization",
      "Content-Language",
      "Content-Type",
      "Origin",
      "X-Request-ID",
    ]
    allow_credentials = true
    max_age           = 86400
  }

  disable_execute_api_endpoint = local.staging_gate_enabled
  authorizer_id                = local.staging_gate_enabled ? one(module.staging_access_gate[*].http_api_authorizer_id) : null

  identity_jwt = local.identity_jwt_native_enforced ? {
    issuer   = local.identity_issuer
    audience = local.identity_audience
  } : null

  identity_jwt_depends_on = local.identity_jwt_native_enforced ? [module.lambda_domain["identity"]] : []

  domain_name     = local.custom_domains_enabled ? local.api_host : null
  certificate_arn = module.api_certificate.certificate_arn
}
