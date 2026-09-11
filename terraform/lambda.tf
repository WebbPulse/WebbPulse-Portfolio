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
