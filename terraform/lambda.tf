locals {
  lambda_function_name = "${local.prefix}-api"

  lambda_table_arns = module.dynamodb.table_arns_list
  lambda_index_arns = [for arn in module.dynamodb.table_arns_list : "${arn}/index/*"]
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

# ---------------------------------------------------------------------------
# The API Lambda from the shared lambda-function module: the execution role,
# the log group and the function. The runtime permission policy below stays in
# the application, because it names this application's tables and secrets.
# ---------------------------------------------------------------------------

module "lambda_api" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/lambda-function"
  version = "~> 1.8"

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
    # The one secret the backend reads: a JSON object read once at cold start.
    # Named outright rather than rebuilt from a prefix, so the function and the
    # secret cannot drift to different names.
    APP_SECRETS_ARN              = module.app_secrets.arns["app"]
    ENVIRONMENT                  = var.environment
    CORS_ORIGINS                 = local.cors_origins
    SITE_URL                     = local.frontend_url
    LOG_LEVEL                    = "INFO"
    POWERTOOLS_SERVICE_NAME      = "webbpulse-api"
    POWERTOOLS_METRICS_NAMESPACE = "WebbPulse"
  }

  # JSON rather than Text so the log group's events parse as JSON, which is what
  # the application errors metric filter in monitoring.tf needs: a JSON filter
  # pattern is only applied to events that parse as JSON, so under Text the
  # filter would match nothing and the alarm would sit in OK forever without
  # anything erroring. The backend logs through AWS Lambda Powertools, which
  # already writes JSON with a top level "level" key, and Lambda does not
  # double encode logs that are already JSON encoded, so records keep that
  # shape and the module default pattern { $.level = "ERROR" } matches them.
  log_retention_days           = 30
  log_format                   = "JSON"
  application_log_level        = "INFO"
  system_log_level             = "INFO"
  set_logging_config_log_group = true

  # aws_iam_role_policy.lambda_api below already grants xray:PutTraceSegments
  # and xray:PutTelemetryRecords, so the module's own inline policy would be
  # redundant. Turning it off keeps this adoption a zero diff change.
  attach_xray_write_policy = false
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
      # Read access to the Secrets Manager secrets holding the signing key and
      # the seeded admin credentials. The module renders the statement so the
      # policy always names exactly the secrets it creates.
      module.app_secrets.read_policy_statement,
    ]
  })
}
