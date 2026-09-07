# ---------------------------------------------------------------------------
# The role GitHub Actions assumes to deploy, from the shared
# github-actions-role module: the account's GitHub OIDC provider, the role and
# its single inline deploy policy.
#
# The statement order below is the order the hand-written policy had, and the
# module renders a one-entry Action or Resource as a bare JSON string the same
# way the hand-written jsonencode() did, so the stored documents do not change.
# ---------------------------------------------------------------------------

# The key the access gate's origin-verify SecureString parameter is encrypted
# with. This is the only remaining SSM read in the application.
data "aws_kms_alias" "ssm" {
  name = "alias/aws/ssm"
}

locals {
  # Behind the staging access gate the backend smoke test calls the API host
  # directly and needs the origin-verify header value from SSM.
  github_actions_gate_statements = [for statement in [
    {
      actions   = ["ssm:GetParameter"]
      resources = [one(module.staging_access_gate[*].origin_verify_ssm_parameter_arn)]
    },
    {
      actions   = ["kms:Decrypt"]
      resources = [data.aws_kms_alias.ssm.target_key_arn]
      condition = {
        StringEquals = { "kms:ViaService" = ["ssm.${var.aws_region}.amazonaws.com"] }
      }
    },
  ] : statement if local.staging_gate_enabled]
}

module "github_actions_role" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/github-actions-role"
  version = "~> 1.1"

  role_name = "${local.prefix}-github-actions-deploy"
  subjects  = ["repo:WebbPulse@185014056/WebbPulse-Portfolio@1029410045:*"]

  policy_statements = concat([
    # Lambda: point the function at the freshly uploaded zip
    {
      actions = [
        "lambda:UpdateFunctionCode",
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration",
        "lambda:PublishVersion",
      ]
      resources = [module.lambda_api.function_arn]
    },
    # S3: upload the Lambda deployment package
    {
      actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
      resources = [module.lambda_artifacts.bucket_arn, "${module.lambda_artifacts.bucket_arn}/*"]
    },
    # S3: sync frontend build artifacts
    {
      actions = [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket",
      ]
      resources = [
        module.frontend.bucket_arn,
        "${module.frontend.bucket_arn}/*",
      ]
    },
    # CloudFront: invalidate the cache after a frontend deploy
    {
      actions = [
        "cloudfront:CreateInvalidation",
        "cloudfront:GetInvalidation",
      ]
      resources = [module.frontend.distribution_arn]
    },
  ], local.github_actions_gate_statements)
}
