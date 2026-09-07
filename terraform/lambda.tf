locals {
  lambda_function_name = "${local.prefix}-api"

  # Every secret is named "<prefix>/<key>", so the prefix is any secret's name
  # with its key stripped. Derived from the module output rather than from
  # local.prefix directly, so a rename of the secrets reaches the function.
  app_secrets_prefix = trimsuffix(module.app_secrets.names["secret-key"], "/secret-key")
  lambda_table_arns  = module.dynamodb.table_arns_list
  lambda_index_arns  = [for arn in module.dynamodb.table_arns_list : "${arn}/index/*"]
}

# ---------------------------------------------------------------------------
# The artifacts bucket CI uploads deployment packages to, from the shared
# lambda-artifacts-bucket module. The archive_file below stays in the
# application: aws_s3_object stores source as the literal path string, and
# path.module inside the module would resolve somewhere else.
# ---------------------------------------------------------------------------

module "lambda_artifacts" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/lambda-artifacts-bucket"
  version = "~> 1.6"

  bucket = "${local.prefix}-lambda-artifacts"

  lifecycle_rule_id                      = "expire-noncurrent"
  noncurrent_version_expiration_days     = 30
  abort_incomplete_multipart_upload_days = 7

  enable_sse = true

  create_placeholder_object      = true
  placeholder_object_key         = "backend/placeholder.zip"
  placeholder_object_source      = data.archive_file.lambda_placeholder.output_path
  placeholder_object_source_hash = data.archive_file.lambda_placeholder.output_base64sha256
}

moved {
  from = aws_s3_bucket.lambda_artifacts
  to   = module.lambda_artifacts.aws_s3_bucket.this
}

moved {
  from = aws_s3_bucket_public_access_block.lambda_artifacts
  to   = module.lambda_artifacts.aws_s3_bucket_public_access_block.this
}

moved {
  from = aws_s3_bucket_versioning.lambda_artifacts
  to   = module.lambda_artifacts.aws_s3_bucket_versioning.this
}

moved {
  from = aws_s3_bucket_server_side_encryption_configuration.lambda_artifacts
  to   = module.lambda_artifacts.aws_s3_bucket_server_side_encryption_configuration.this[0]
}

moved {
  from = aws_s3_bucket_lifecycle_configuration.lambda_artifacts
  to   = module.lambda_artifacts.aws_s3_bucket_lifecycle_configuration.this
}

moved {
  from = aws_s3_object.lambda_placeholder
  to   = module.lambda_artifacts.aws_s3_object.placeholder[0]
}

data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/.terraform/lambda-placeholder.zip"

  source {
    filename = "app/__init__.py"
    content  = ""
  }

  source {
    filename = "app/lambda_handler.py"
    content  = <<-PY
      import json


      def handler(event, context):
          return {
              "statusCode": 503,
              "headers": {"Content-Type": "application/json"},
              "body": json.dumps({"detail": "not deployed"}),
          }
    PY
  }
}

data "aws_kms_alias" "ssm" {
  name = "alias/aws/ssm"
}

# ---------------------------------------------------------------------------
# The API Lambda from the shared lambda-function module: the execution role,
# the log group and the function. The runtime permission policy below stays in
# the application, because it names this application's tables and parameters.
# ---------------------------------------------------------------------------

module "lambda_api" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/lambda-function"
  version = "~> 1.6"

  function_name = local.lambda_function_name
  role_name     = "${local.prefix}-api-lambda"

  runtime       = "python3.13"
  handler       = "app.lambda_handler.handler"
  architectures = ["arm64"]
  memory_size   = 512
  timeout       = 15

  code = {
    s3_bucket        = module.lambda_artifacts.bucket_id
    s3_key           = module.lambda_artifacts.placeholder_object_key
    source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256
  }

  environment_variables = {
    DYNAMODB_TABLE_PREFIX = local.prefix
    # The backend builds each secret's name as <SECRETS_PREFIX>/<key>. Taken
    # from the module's own output rather than rebuilt from local.prefix, so
    # the function depends on the secrets existing and the two cannot drift to
    # different names.
    SECRETS_PREFIX = local.app_secrets_prefix
    # Kept alongside SECRETS_PREFIX for one change only. This apply and the CI
    # backend deploy race after the merge, so for a few minutes either version
    # of the code can be running against this environment. With both variables
    # present the old code still finds its SSM prefix and the new code finds
    # its secrets prefix, whichever lands first, in staging and again in
    # production. The code in this change never reads it. Removed in the next
    # change together with the SSM parameters themselves.
    SSM_PARAMETER_PREFIX         = "/${local.prefix}"
    ENVIRONMENT                  = var.environment
    CORS_ORIGINS                 = local.cors_origins
    SITE_URL                     = local.frontend_url
    LOG_LEVEL                    = "INFO"
    POWERTOOLS_SERVICE_NAME      = "webbpulse-api"
    POWERTOOLS_METRICS_NAMESPACE = "WebbPulse"
  }

  log_retention_days           = 30
  log_format                   = "Text"
  set_logging_config_log_group = true
}

moved {
  from = aws_iam_role.lambda_api
  to   = module.lambda_api.aws_iam_role.this
}

moved {
  from = aws_cloudwatch_log_group.lambda_api
  to   = module.lambda_api.aws_cloudwatch_log_group.this
}

moved {
  from = aws_lambda_function.api
  to   = module.lambda_api.aws_lambda_function.this
}

resource "aws_iam_role_policy" "lambda_api" {
  name = "api-runtime"
  role = module.lambda_api.role_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${module.lambda_api.log_group_arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
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
        Resource = concat(local.lambda_table_arns, local.lambda_index_arns)
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${local.prefix}/*"
      },
      # Read access to the Secrets Manager secrets the backend moves onto. The
      # grant lands before the backend reads them so the switch in the next
      # change is a deploy rather than a deploy plus an apply. The SSM statement
      # above stays until the backend has stopped reading parameters.
      module.app_secrets.read_policy_statement,
      {
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = data.aws_kms_alias.ssm.target_key_arn
        Condition = {
          StringEquals = { "kms:ViaService" = "ssm.${var.aws_region}.amazonaws.com" }
        }
      },
    ]
  })
}
