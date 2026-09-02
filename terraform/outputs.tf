output "aws_account_id" {
  description = "AWS account ID Terraform is deploying into"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS region being deployed to"
  value       = data.aws_region.current.name
}

output "webbpulse_zone_id" {
  description = "Route53 hosted zone ID for webbpulse.com"
  value       = var.route53_zone_id
}

output "frontend_url" {
  description = "CloudFront URL for the frontend"
  value       = "https://www.webbpulse.com"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID — used by CI/CD to invalidate cache after deploys"
  value       = aws_cloudfront_distribution.frontend.id
}

output "frontend_bucket" {
  description = "S3 bucket name for frontend asset uploads"
  value       = aws_s3_bucket.frontend.bucket
}

output "backend_url" {
  description = "Public API URL (App Runner custom domain)"
  value       = "https://api.webbpulse.com"
}

output "ecr_repository_url" {
  description = "ECR repository URL — push Docker images here before first App Runner deploy"
  value       = aws_ecr_repository.backend.repository_url
}

output "db_endpoint" {
  description = "RDS endpoint (host:port) — publicly reachable, SSL required"
  value       = aws_db_instance.main.endpoint
}
