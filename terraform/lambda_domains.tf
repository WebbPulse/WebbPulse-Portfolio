locals {
  lambda_domains = {
    content = {
      secrets     = true
      memory      = 512
      tables      = ["posts", "categories", "site-content", "meta"]
      read_tables = ["users"]
    }
    resume = {
      secrets     = true
      memory      = 512
      tables      = ["projects", "experience", "skills", "education", "certifications", "meta"]
      read_tables = ["site-content", "users"]
    }
    identity = {
      secrets     = true
      memory      = 512
      tables      = ["users", "rate-limits", "meta"]
      read_tables = []
    }
    public = {
      secrets     = false
      memory      = 256
      tables      = []
      read_tables = ["posts", "site-content"]
    }
  }

  dynamodb_write_actions = [
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:UpdateItem",
    "dynamodb:DeleteItem",
    "dynamodb:Query",
    "dynamodb:Scan",
    "dynamodb:BatchGetItem",
    "dynamodb:BatchWriteItem",
    "dynamodb:TransactWriteItems",
    "dynamodb:TransactGetItems",
    "dynamodb:DescribeTable",
    "dynamodb:ConditionCheckItem",
  ]

  dynamodb_read_actions = [
    "dynamodb:GetItem",
    "dynamodb:Query",
    "dynamodb:Scan",
    "dynamodb:BatchGetItem",
    "dynamodb:DescribeTable",
  ]

  lambda_domain_write_arns = {
    for name, domain in local.lambda_domains : name => flatten([
      for table in domain.tables : [
        module.dynamodb.table_arns[table],
        "${module.dynamodb.table_arns[table]}/index/*",
      ]
    ])
  }

  lambda_domain_read_arns = {
    for name, domain in local.lambda_domains : name => flatten([
      for table in domain.read_tables : [
        module.dynamodb.table_arns[table],
        "${module.dynamodb.table_arns[table]}/index/*",
      ]
    ])
  }
}

variable "bootstrap_image_tag" {
  description = "Image tag seeding every per-domain function at create time. It must already exist in all four ECR repositories; image_uri is ignored thereafter, so deploys own it."
  type        = string

  validation {
    condition     = can(regex("^sha-[0-9a-f]{40}$", var.bootstrap_image_tag))
    error_message = "bootstrap_image_tag must be sha- followed by a full 40 character commit sha, which is the tag the container image build pushes."
  }
}

module "lambda_domain" {
  for_each = local.lambda_domains

  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/lambda-function"
  version = "~> 2.1"

  function_name = "${local.prefix}-${each.key}"
  role_name     = "${local.prefix}-${each.key}-lambda"

  package_type = "Image"

  architectures = ["arm64"]
  memory_size   = each.value.memory

  timeout = 15

  code = {
    image_uri = "${module.registry.repository_urls[each.key]}:${var.bootstrap_image_tag}"
  }

  environment_variables = merge(
    {
      DYNAMODB_TABLE_PREFIX = local.prefix
      ENVIRONMENT           = var.environment
      SERVICE_NAME          = "webbpulse-portfolio-${each.key}"
      CORS_ORIGINS          = local.cors_origins
      SITE_URL              = local.frontend_url
      LOG_LEVEL             = "INFO"

      WEBBPULSE_OTEL_SAMPLE_RATIO        = var.environment == "production" ? "0.1" : "1.0"
      OTEL_EXPORTER_OTLP_TRACES_ENDPOINT = "https://xray.${var.aws_region}.amazonaws.com/v1/traces"
    },
    each.value.secrets ? { APP_SECRETS_ARN = module.app_secrets.arns["app"] } : {},

    each.key == "identity" ? merge({
      IDENTITY_ENVIRONMENT       = var.environment
      IDENTITY_RP_NAME           = var.identity_rp_name
      IDENTITY_PRODUCT_NAME      = "WebbPulse Portfolio"
      IDENTITY_SUPPORT_EMAIL     = "support@${local.domain}"
      IDENTITY_FRONTEND_BASE_URL = "https://${local.domain}"

      IDENTITY_EMAIL_FROM            = local.identity_email_from
      IDENTITY_SES_CONFIGURATION_SET = local.identity_ses_configuration_set
      IDENTITY_REGISTRATION_ENABLED  = "false"

      IDENTITY_OAUTH_REDIRECT_URIS = local.identity_oauth_redirect_uris
      IDENTITY_GOOGLE_CLIENT_ID    = var.oauth_google_client_id
      IDENTITY_GITHUB_CLIENT_ID    = var.oauth_github_client_id

      IDENTITY_PASSKEYS_ENABLED      = tostring(local.passkeys_enabled)
      IDENTITY_PASSKEYS_PASSWORDLESS = tostring(local.passkeys_passwordless)
      IDENTITY_WEBAUTHN_ORIGINS      = local.identity_webauthn_origins
      },

    module.identity.identity_environment) : {},
  )

  log_retention_days           = 7
  log_format                   = "JSON"
  application_log_level        = "INFO"
  system_log_level             = "INFO"
  set_logging_config_log_group = true

  tracing_mode             = "Active"
  attach_xray_write_policy = true
}

resource "aws_iam_role_policy" "lambda_domain" {
  for_each = local.lambda_domains

  name = "${each.key}-runtime"
  role = module.lambda_domain[each.key].role_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid      = "WriteOwnLogs"
          Effect   = "Allow"
          Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = "${module.lambda_domain[each.key].log_group_arn}:*"
        },
        {
          Sid      = "WriteSpansToTheXRayOTLPEndpoint"
          Effect   = "Allow"
          Action   = ["xray:PutSpans", "xray:PutSpansForIndexing"]
          Resource = "*"
        },
      ],
      length(local.lambda_domain_write_arns[each.key]) > 0 ? [
        {
          Sid      = "ReadWriteOwnTables"
          Effect   = "Allow"
          Action   = local.dynamodb_write_actions
          Resource = local.lambda_domain_write_arns[each.key]
        },
      ] : [],
      length(local.lambda_domain_read_arns[each.key]) > 0 ? [
        {
          Sid      = "ReadSharedTables"
          Effect   = "Allow"
          Action   = local.dynamodb_read_actions
          Resource = local.lambda_domain_read_arns[each.key]
        },
      ] : [],
      each.value.secrets ? [module.app_secrets.read_policy_statement] : [],
    )
  })
}
