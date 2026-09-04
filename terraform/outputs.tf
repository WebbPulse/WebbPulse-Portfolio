output "aws_account_id" {
  description = "AWS account ID Terraform is deploying into"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS region being deployed to"
  value       = data.aws_region.current.name
}

output "webbpulse_zone_id" {
  description = "Route53 hosted zone ID of the parent zone (webbpulse.com)"
  value       = var.route53_zone_id
}

output "staging_zone_name_servers" {
  description = "Name servers of the staging child zone, null in production or when custom domains are disabled"
  value       = one(aws_route53_zone.staging[*].name_servers)
}

output "frontend_url" {
  description = "Public frontend URL"
  value       = local.frontend_url
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
  description = "Public API base URL (custom domain when enabled, otherwise the HTTP API endpoint)"
  value       = local.api_url
}

output "api_gateway_url" {
  description = "Default HTTP API endpoint for the Lambda backend"
  value       = aws_apigatewayv2_api.backend.api_endpoint
}

output "api_custom_domain" {
  description = "Regional target hostname of the API Gateway custom domain, null when custom domains are disabled"
  value       = one(aws_apigatewayv2_domain_name.api[*].domain_name_configuration[0].target_domain_name)
}

output "lambda_function_name" {
  description = "Lambda function name — CI/CD updates its code after each backend push"
  value       = aws_lambda_function.api.function_name
}

output "lambda_artifact_bucket" {
  description = "S3 bucket CI/CD uploads Lambda deployment packages to"
  value       = aws_s3_bucket.lambda_artifacts.bucket
}

output "dynamodb_table_names" {
  description = "DynamoDB table names keyed by entity"
  value       = { for k, t in aws_dynamodb_table.this : k => t.name }
}
