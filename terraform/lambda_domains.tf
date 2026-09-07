# ---------------------------------------------------------------------------
# The four per-domain FastAPI functions, delivered as container images and run
# under the AWS Lambda Web Adapter. Section 3.3 of
# docs/migration/pilot-split-plan.md.
#
# The monolith in lambda.tf is deliberately untouched. It still serves every
# route, because this file creates functions and nothing routes to them yet:
# apigateway.tf keeps its single "legacy" integration until the four cuts in
# section 6. That is what makes this change additive, and what makes it safe to
# apply before a single request has ever reached one of these images.
#
# Every AWS_LWA_* setting is baked into the image by backend/Dockerfile
# (AWS_LWA_PORT, AWS_LWA_READINESS_CHECK_PATH, AWS_LWA_READINESS_CHECK_PROTOCOL
# and AWS_LWA_ASYNC_INIT), so none is repeated here. Repeating one would put two
# sources of truth on the same setting and let them drift.
# ---------------------------------------------------------------------------

locals {
  # One entry per deployable domain. `secrets` is whether the function reads the
  # webbpulse-<env>/app secret at all; `tables` names the tables it writes and
  # `read_tables` the ones it only reads, both as keys of module.dynamodb, so
  # every ARN comes out of the module rather than being rebuilt by hand.
  #
  # Memory and timeout match the monolith at 512 MB and 15 seconds, except
  # `public`, whose four routes do at most one DynamoDB read each.
  #
  # The seeding note is the one place where reading the code changed the
  # answer. Section 1's ownership table gives `content` read only access to
  # `users` and gives `identity` nothing on `site-content`. But
  # app/core/middleware.py's SeedMiddleware calls ensure_admin_seeded() and
  # ensure_site_content_seeded() together on the first request of a process,
  # and app/composition/wiring.py adds that one middleware to both domains that
  # set `seeds = true`, which is `content` and `identity`. So on its first
  # request `content` writes `users` and `identity` writes `site-content`,
  # whatever the ownership table says. Denying either write would fail the
  # first request of every cold start on a table the domain does not own, so
  # both are granted and the divergence is recorded here rather than left as a
  # surprise in CloudWatch. The same middleware is why `content` reads the
  # admin credentials out of the one app secret and not just SECRET_KEY.
  #
  # `meta` is shared infrastructure, not identity's table. Repository.create in
  # app/db/repository.py writes a COUNTER# item and a UNIQUE# item for every
  # entity it creates, in the same transaction as the entity itself, so every
  # domain that writes anything needs read and write on `meta`. `public` writes
  # nothing and so does not appear there.
  lambda_domains = {
    content = {
      secrets     = true
      memory      = 512
      tables      = ["posts", "categories", "site-content", "meta", "users"]
      read_tables = []
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
      tables      = ["users", "rate-limits", "meta", "site-content"]
      read_tables = []
    }
    public = {
      secrets     = false
      memory      = 256
      tables      = []
      read_tables = ["posts", "site-content"]
    }
  }

  # DynamoDB actions a domain gets on a table it writes. This is the same list
  # the monolith's runtime policy carries, so a domain moving off the monolith
  # cannot lose an action it was relying on.
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

  # And on a table it only reads. TransactGetItems and ConditionCheckItem are
  # left out on purpose: nothing in a read only path uses them, and including
  # them would blur the line the least privilege claim rests on.
  dynamodb_read_actions = [
    "dynamodb:GetItem",
    "dynamodb:Query",
    "dynamodb:Scan",
    "dynamodb:BatchGetItem",
    "dynamodb:DescribeTable",
  ]

  # Table and index ARNs per domain, resolved through module.dynamodb so a
  # renamed or re-keyed table is a plan error rather than a runtime denial. The
  # /index/* wildcard is needed wherever a Query names an index: `public` reads
  # posts through published-index, and `content` writes through both of the
  # posts indexes.
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
  description = "Image tag used as the seed for every per-domain function, as pushed to ECR by the container image build in deploy-backend.yml. Lambda pulls and optimises the image when it creates the function, so a tag that does not resolve fails the create: the tag named here must already exist in all four repositories before the first apply. It is only ever a seed, because image_uri is on the lambda-function module's ignore_changes list, so the deploy step's UpdateFunctionCode is not undone by the next plan and this value never needs changing again."
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

  # An Image function takes neither runtime nor handler: the image supplies
  # both, and the module rejects either one alongside package_type = "Image".
  # No image_config either, because the Dockerfile already declares the CMD
  # that starts this domain's entrypoint.
  package_type = "Image"

  # arm64, matching the monolith. The base image is a multi-architecture
  # manifest, so the image build produces an arm64 variant either way.
  architectures = ["arm64"]
  memory_size   = each.value.memory

  # 15 seconds, matching the monolith and comfortably under the HTTP API
  # integration's own 29 second ceiling.
  timeout = 15

  # The seed only. The repository URL comes from module.registry rather than
  # being rebuilt from the account id and the region, so the function and the
  # repository cannot drift to different names.
  code = {
    image_uri = "${module.registry.repository_urls[each.key]}:${var.bootstrap_image_tag}"
  }

  # The names the shared package's BaseServiceSettings and Portfolio's own
  # Settings subclass read. Two renames travel with the split: today's
  # CORS_ORIGINS keeps its name here because app/composition/settings.py still
  # declares CORS_ORIGINS and derives the base class's cors_allow_origins from
  # it, and the two POWERTOOLS_* variables are absent because a domain function
  # logs through webbpulse.logging rather than Powertools.
  #
  # SERVICE_NAME has to match SERVICE_NAME_TEMPLATE in
  # app/composition/wiring.py, because that string becomes the OpenTelemetry
  # service.name and the service field on every log line.
  #
  # APP_SECRETS_ARN is set only for the domains that read a secret. `public`
  # reads none, which is what lets its role hold no secretsmanager action at
  # all, and an ARN it could not read would be a misleading configuration.
  environment_variables = merge(
    {
      DYNAMODB_TABLE_PREFIX = local.prefix
      ENVIRONMENT           = var.environment
      SERVICE_NAME          = "webbpulse-portfolio-${each.key}"
      CORS_ORIGINS          = local.cors_origins
      SITE_URL              = local.frontend_url
      LOG_LEVEL             = "INFO"
    },
    each.value.secrets ? { APP_SECRETS_ARN = module.app_secrets.arns["app"] } : {},
  )

  # 7 days, the retention the platform migration decision settled on, and
  # created by Terraform rather than lazily by Lambda so the retention is in
  # place from the first invoke instead of after the group has already
  # collected a run of never expiring events.
  log_retention_days           = 7
  log_format                   = "JSON"
  application_log_level        = "INFO"
  system_log_level             = "INFO"
  set_logging_config_log_group = true

  # Unlike the monolith, whose runtime policy carried the two X-Ray actions
  # before the module owned them, these roles are new, so the module attaches
  # its own X-Ray write policy and the runtime policy below does not repeat it.
  tracing_mode             = "Active"
  attach_xray_write_policy = true
}

# ---------------------------------------------------------------------------
# One runtime policy per domain, naming only that domain's tables. X-Ray is not
# here: the module attaches it. Logs are, because the module creates the log
# group but leaves writing to it to the application, the same way the
# monolith's policy does.
# ---------------------------------------------------------------------------

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
      # The one app secret, and only for the domains that read it. The module
      # renders the statement so the policy always names exactly the secret it
      # creates rather than a prefix that could widen underneath it.
      each.value.secrets ? [module.app_secrets.read_policy_statement] : [],
    )
  })
}
