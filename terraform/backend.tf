resource "aws_ecr_repository" "backend" {
  count = local.legacy_count

  name                 = "${local.prefix}-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "backend" {
  count = local.legacy_count

  repository = aws_ecr_repository.backend[0].name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 3 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_iam_role" "apprunner_ecr_access" {
  count = local.legacy_count

  name = "${local.prefix}-apprunner-ecr-access"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "build.apprunner.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "apprunner_ecr_access" {
  count = local.legacy_count

  role       = aws_iam_role.apprunner_ecr_access[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

resource "aws_iam_role" "apprunner_instance" {
  count = local.legacy_count

  name = "${local.prefix}-apprunner-instance"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "tasks.apprunner.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "apprunner_ssm" {
  count = local.legacy_count

  name = "ssm-read"
  role = aws_iam_role.apprunner_instance[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameters", "ssm:GetParameter"]
      Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${local.prefix}/*"
    }]
  })
}

resource "aws_apprunner_service" "backend" {
  count = local.legacy_count

  service_name = "${local.prefix}-backend"

  source_configuration {
    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_ecr_access[0].arn
    }

    image_repository {
      image_identifier      = "${aws_ecr_repository.backend[0].repository_url}:latest"
      image_repository_type = "ECR"

      image_configuration {
        port = "8000"

        runtime_environment_secrets = {
          DATABASE_URL   = aws_ssm_parameter.database_url[0].arn
          SECRET_KEY     = aws_ssm_parameter.secret_key.arn
          ADMIN_USERNAME = aws_ssm_parameter.admin_username.arn
          ADMIN_PASSWORD = aws_ssm_parameter.admin_password.arn
          ADMIN_EMAIL    = aws_ssm_parameter.admin_email.arn
        }

        runtime_environment_variables = {
          ENVIRONMENT  = var.environment
          CORS_ORIGINS = local.cors_origins
        }
      }
    }

    # Deployments triggered by CI/CD pushing to ECR, not by Terraform
    auto_deployments_enabled = false
  }

  instance_configuration {
    cpu               = "0.25 vCPU"
    memory            = "0.5 GB"
    instance_role_arn = aws_iam_role.apprunner_instance[0].arn
  }

  # Explicit DEFAULT egress. Terraform treats this block as computed, so
  # simply removing it does NOT revert a previously configured VPC egress —
  # the value must be set explicitly to force the switch away from VPC.
  network_configuration {
    egress_configuration {
      egress_type = "DEFAULT"
    }

    ingress_configuration {
      is_publicly_accessible = true
    }
  }

  # CI/CD manages the deployed image tag — don't let Terraform roll it back
  lifecycle {
    ignore_changes = [
      source_configuration[0].image_repository[0].image_identifier,
    ]
  }
}

resource "aws_apprunner_custom_domain_association" "api" {
  count = local.legacy_enabled && local.custom_domains_enabled ? 1 : 0

  service_arn          = aws_apprunner_service.backend[0].arn
  domain_name          = local.api_host
  enable_www_subdomain = false
}
