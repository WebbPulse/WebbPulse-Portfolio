resource "aws_iam_openid_connect_provider" "github_actions" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

import {
  for_each = var.environment == "production" ? toset(["production"]) : toset([])
  to       = aws_iam_openid_connect_provider.github_actions
  id       = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
}

resource "aws_iam_role" "github_actions_deploy" {
  name = "${local.prefix}-github-actions-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github_actions.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:WebbPulse@185014056/WebbPulse-Portfolio@1029410045:*"
          }
        }
      }
    ]
  })
}

locals {
  # Behind the staging access gate the backend smoke test calls the API host
  # directly and needs the origin-verify header value from SSM.
  github_actions_gate_statements = [for statement in [
    {
      Effect   = "Allow"
      Action   = "ssm:GetParameter"
      Resource = one(module.staging_access_gate[*].origin_verify_ssm_parameter_arn)
    },
    {
      Effect   = "Allow"
      Action   = "kms:Decrypt"
      Resource = data.aws_kms_alias.ssm.target_key_arn
      Condition = {
        StringEquals = { "kms:ViaService" = "ssm.${var.aws_region}.amazonaws.com" }
      }
    },
  ] : statement if local.staging_gate_enabled]

  github_actions_statements = concat([
    {
      Effect = "Allow"
      Action = [
        "lambda:UpdateFunctionCode",
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration",
        "lambda:PublishVersion",
      ]
      Resource = aws_lambda_function.api.arn
    },
    {
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
      Resource = [aws_s3_bucket.lambda_artifacts.arn, "${aws_s3_bucket.lambda_artifacts.arn}/*"]
    },
    {
      Effect = "Allow"
      Action = [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket",
      ]
      Resource = [
        module.frontend.bucket_arn,
        "${module.frontend.bucket_arn}/*",
      ]
    },
    {
      Effect = "Allow"
      Action = [
        "cloudfront:CreateInvalidation",
        "cloudfront:GetInvalidation",
      ]
      Resource = module.frontend.distribution_arn
    },
  ], local.github_actions_gate_statements)
}

resource "aws_iam_role_policy" "github_actions_deploy" {
  name = "deploy-permissions"
  role = aws_iam_role.github_actions_deploy.id

  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = local.github_actions_statements
  })
}
