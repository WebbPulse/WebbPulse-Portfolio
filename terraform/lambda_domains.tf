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
  # Seeding is per table, and that is what puts these grants back on section
  # 1's ownership table. SeedMiddleware used to call ensure_admin_seeded() and
  # ensure_site_content_seeded() together wherever it was added, so `content`
  # wrote `users` and `identity` wrote `site-content` on the first request of
  # every cold start, and both writes had to be granted here. That is no longer
  # what the code does: `SeedMiddleware` now takes the seeder names to run,
  # `Domain.seeds` in app/composition/wiring.py names only the seeds a domain
  # owns, and app/core/middleware.py's SEEDERS maps them. `content` seeds
  # `site_content` and `identity` seeds `admin`, so each writes only its own
  # table and neither reaches across. The two cross-domain writes are therefore
  # dropped: `content` reads `users` for admin authorisation and no longer
  # writes it, and `identity` neither reads nor writes `site-content`. Narrowing
  # the seeders is also why `content` needs only SECRET_KEY out of the one app
  # secret rather than the three admin credentials.
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
  #
  # The two OTEL_ variables are the whole tracing contract webbpulse 0.2.0
  # keeps. `configure_tracing` builds the pipeline itself rather than running
  # under `opentelemetry-instrument`, so OTEL_EXPORTER_OTLP_TRACES_PROTOCOL,
  # OTEL_PYTHON_DISTRO, OTEL_PYTHON_CONFIGURATOR and OTEL_TRACES_SAMPLER are
  # not set here: the protocol is implicit in the exporter class the package
  # constructs, the distribution is used as a library rather than a launcher,
  # and the sampler is passed explicitly so a ratio sampler in the environment
  # cannot pre-drop the spans the tail step exists to judge.
  #
  # WEBBPULSE_OTEL_SAMPLE_RATIO is the probability a *non-error* trace is kept.
  # Errors are kept whatever it says, which is the point of tail sampling and
  # is why 0.1 on production is not the 90 percent loss of failures that a head
  # sampler at the same ratio would be. Staging keeps everything because its
  # traffic is this repository's own tests.
  environment_variables = merge(
    {
      DYNAMODB_TABLE_PREFIX = local.prefix
      ENVIRONMENT           = var.environment
      SERVICE_NAME          = "webbpulse-portfolio-${each.key}"
      CORS_ORIGINS          = local.cors_origins
      SITE_URL              = local.frontend_url
      LOG_LEVEL             = "INFO"

      WEBBPULSE_OTEL_SAMPLE_RATIO = var.environment == "production" ? "0.1" : "1.0"
      # Set explicitly rather than left to the package's own default, which
      # derives the same URL from AWS_REGION. Naming it here is what makes the
      # destination visible in the plan and in the console, so a function
      # exporting nowhere is a diff rather than an archaeology exercise.
      OTEL_EXPORTER_OTLP_TRACES_ENDPOINT = "https://xray.${var.aws_region}.amazonaws.com/v1/traces"
    },
    each.value.secrets ? { APP_SECRETS_ARN = module.app_secrets.arns["app"] } : {},

    # The identity standard's M0 spike, on the identity function only and only
    # when var.identity_spike_enabled is set. With the spike off this merge
    # contributes an empty map, so no other domain and no production plan sees
    # any of it. identity_spike.tf has the whole rationale.
    #
    # IDENTITY_SIGNING_KEY_ID is the alias, `alias/webbpulse-<env>-identity-signing`,
    # not the key id or the key ARN, and that avoids a dependency cycle rather
    # than merely being tidier. The key policy in identity_spike.tf names
    # module.lambda_domain["identity"].role_arn as a principal, so the key
    # depends on this module; naming aws_kms_key.identity_signing[0].key_id here
    # would make this module depend on the key, and Terraform would refuse the
    # graph. The alias name is a pure function of local.prefix, so it closes the
    # loop with a string. KMS accepts an alias anywhere it accepts a key id for
    # Sign and GetPublicKey, and the alias is created from the same local, so
    # the two cannot drift.
    #
    # The issuer and audience are passed rather than derived in the application
    # for the reason identity_spike.tf gives at length: the authorizer and the
    # signer have to agree on both strings byte for byte, and the only way to
    # guarantee that is for both to read the same Terraform local.
    each.key == "identity" && local.identity_spike_enabled ? {
      IDENTITY_SPIKE_ENABLED  = "true"
      IDENTITY_SIGNING_KEY_ID = "alias/${local.prefix}-identity-signing"
      IDENTITY_TOKEN_ISSUER   = local.identity_spike_issuer
      IDENTITY_TOKEN_AUDIENCE = local.identity_spike_audience
    } : {},

    # The identity standard's M1, on the identity function only and in every
    # environment. Unlike the spike block above there is no flag: from M1 the
    # discovery document and the JWKS are what this product publishes about
    # itself rather than an experiment's exhaust, so they are unconditional.
    # identity.tf has the full rationale.
    #
    # Every name here is a field of `webbpulse.identity.IdentitySettings`, whose
    # env_prefix is `IDENTITY_`, so the composition root builds the settings
    # object straight from the environment with no per-field plumbing. Adding a
    # setting is one line here and none in Python, which is the point of the
    # prefix.
    #
    # IDENTITY_SIGNING_KEY_ARNS is a JSON array rather than the alias the spike
    # passes, and rather than a bare comma separated string. Three reasons, in
    # order of how much they cost to get wrong:
    #
    #  1. It is a list because section 3.5's rotation is "add a key, deploy,
    #     wait, promote, deploy, drop", and every one of those steps is an edit
    #     to this list. A scalar would have to be widened by the change that
    #     first needs two keys, which is the change least able to afford a
    #     refactor.
    #  2. JSON rather than CSV because IdentitySettings deliberately refuses
    #     bare CSV for list fields: these are ARNs, and a stray comma should be
    #     an error rather than a silently split entry.
    #  3. The real ARN rather than the alias, because two aliases would have to
    #     be created and swapped in lockstep to express a two key overlap.
    #
    # Naming the key ARN here does not close the dependency cycle the spike's
    # comment above avoids, and the difference is worth stating because the two
    # blocks look contradictory. The cycle exists when the *key* is built from
    # something this module produces and this module is built from the key.
    # aws_kms_key.identity_signing takes module.lambda_domain["identity"].role_arn
    # in its key policy, so the key depends on the role. The role is created by
    # this module, but the environment variables are an attribute of the
    # function, not of the role, and Terraform's graph is per resource rather
    # than per module: role, then key, then function. The alias indirection is
    # what the spike needed because it wrote the variable at a point where it
    # would have referenced the key resource from the same module call that the
    # key's policy references back.
    #
    # IDENTITY_ISSUER and IDENTITY_AUDIENCE are passed rather than derived in
    # the application, for the reason identity.tf gives at length: the gateway
    # and the signer have to agree on both strings byte for byte, and the only
    # way to guarantee that is for both to read the same Terraform local.
    #
    # IDENTITY_ENVIRONMENT is separate from ENVIRONMENT above even though both
    # carry the same value. IdentitySettings has its own `environment` field
    # under the same `IDENTITY_` prefix, and it gates exactly two things: the
    # refusal of a plaintext http issuer, and the local development fallbacks.
    # Letting it default to `local` in a deployed function would silently switch
    # both of those to their permissive setting, so it is set explicitly.
    #
    # IDENTITY_COOKIE_DOMAIN and IDENTITY_RP_ID are the registrable domain
    # rather than the API host. Neither is read by a route in 0.9.0, since the
    # refresh cookie is M2 and passkeys are M5, but rp_id is hashed into every
    # credential and immutable for that credential's life (section 6.1), so it
    # is set now while it is still free to change.
    each.key == "identity" ? {
      IDENTITY_ENVIRONMENT       = var.environment
      IDENTITY_ISSUER            = local.identity_issuer
      IDENTITY_AUDIENCE          = local.identity_audience
      IDENTITY_SIGNING_KEY_ARNS  = jsonencode(local.identity_signing_key_arns)
      IDENTITY_COOKIE_DOMAIN     = local.identity_registrable_domain
      IDENTITY_RP_ID             = local.identity_registrable_domain
      IDENTITY_RP_NAME           = "WebbPulse Portfolio"
      IDENTITY_PRODUCT_NAME      = "WebbPulse Portfolio"
      IDENTITY_SUPPORT_EMAIL     = "support@${local.domain}"
      IDENTITY_FRONTEND_BASE_URL = "https://${local.domain}"
    } : {},
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
  # its own X-Ray write policy and the runtime policy below does not repeat
  # xray:PutTraceSegments or xray:PutTelemetryRecords. It does add xray:PutSpans,
  # which the module's policy does not carry; see the statement below.
  tracing_mode             = "Active"
  attach_xray_write_policy = true
}

# ---------------------------------------------------------------------------
# One runtime policy per domain, naming only that domain's tables. Logs are
# here, because the module creates the log group but leaves writing to it to
# the application, the same way the monolith's policy does.
#
# X-Ray is here only in part. The module's attach_xray_write_policy grants
# xray:PutTraceSegments and xray:PutTelemetryRecords, which are the two actions
# the X-Ray *segment* API takes and the two the Lambda service itself needs for
# Active tracing, so those are not repeated. They are not the actions the OTLP
# endpoint takes: `POST https://xray.<region>.amazonaws.com/v1/traces` is
# authorized by xray:PutSpans, and that is the call webbpulse 0.2.0's
# OTLPAwsSpanExporter makes on every flush. Neither the module's inline policy
# nor the AWS managed AWSXrayWriteOnlyAccess carries it: that policy was last
# edited in 2018 and grants PutTraceSegments, PutTelemetryRecords and the three
# GetSampling* actions and nothing else. So without the statement below every
# export is a 403, which the exporter retries in silence, and the symptom is
# that traces never appear with nothing in the logs to say why.
#
# xray:PutSpansForIndexing is granted alongside it. Both actions are in the
# X-Ray service authorization reference at Write level, and the pair is what
# Transaction Search indexes a span through; PutSpans alone would export the
# span and leave it unsearchable. Neither action takes a resource-level
# permission, so "*" is the only resource either accepts.
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
      # The one app secret, and only for the domains that read it. The module
      # renders the statement so the policy always names exactly the secret it
      # creates rather than a prefix that could widen underneath it.
      each.value.secrets ? [module.app_secrets.read_policy_statement] : [],
    )
  })
}
