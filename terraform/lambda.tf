# ---------------------------------------------------------------------------
# What is left of the monolith's Terraform after section 6's retirement.
#
# The monolith function, its execution role, its runtime policy and its log
# group are gone: module.lambda_api and aws_iam_role_policy.lambda_api were
# deleted by the PR that retired it, along with the `legacy` integration in
# apigateway.tf that was the only thing routing to it. The four per-domain
# functions in lambda_domains.tf serve every route now.
#
# The artifacts bucket stays, and stays deliberately. It holds the zips the
# monolith was deployed from, and the last of them is the rollback vehicle: if
# the retirement has to be undone, re-adding module.lambda_api and pointing its
# `code` at the object recorded in docs/migration/cutover-log.md is what brings
# the monolith back. Destroying the bucket would destroy that. The bucket costs
# a few cents a month and its lifecycle rule already expires noncurrent
# versions after 30 days, so keeping it is cheap and deleting it is not
# reversible. Retire it in a later PR once the rollback window has closed.
#
# The placeholder archive stays with it: it is the bucket module's
# create_placeholder_object source, so removing it would be a change to the
# bucket rather than a tidy-up.
# ---------------------------------------------------------------------------

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
