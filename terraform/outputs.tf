output "aws_account_id" {
  description = "AWS account ID Terraform is deploying into"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS region being deployed to"
  value       = data.aws_region.current.region
}

output "webbpulse_zone_id" {
  description = "Route53 hosted zone ID of the parent zone (webbpulse.com)"
  value       = var.route53_zone_id
}

output "staging_zone_name_servers" {
  description = "Name servers of the staging child zone, null in production or when custom domains are disabled"
  value       = module.staging_dns.name_servers
}

output "frontend_url" {
  description = "Public frontend URL"
  value       = local.frontend_url
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID, used by CI/CD to invalidate the cache after deploys"
  value       = module.frontend.distribution_id
}

output "frontend_bucket" {
  description = "S3 bucket name for frontend asset uploads"
  value       = module.frontend.bucket_name
}

output "backend_url" {
  description = "Public API base URL (custom domain when enabled, otherwise the HTTP API endpoint)"
  value       = local.api_url
}

output "frontend_api_base_url" {
  description = "Base URL the frontend build must call, set as the API_BASE_URL GitHub environment variable"
  value       = local.frontend_api_url
}

output "api_gateway_url" {
  description = "Default HTTP API endpoint for the Lambda backend"
  value       = module.api.api_endpoint
}

output "api_custom_domain" {
  description = "Regional target hostname of the API Gateway custom domain, null when custom domains are disabled"
  value       = module.api.custom_domain_target_domain_name
}

output "lambda_artifact_bucket" {
  description = "S3 bucket holding the archived backend deployment zips, retained as the rollback source"
  value       = module.lambda_artifacts.bucket_id
}

output "dynamodb_table_names" {
  description = "DynamoDB table names keyed by entity"
  value       = module.dynamodb.table_names
}

output "staging_access_gate_hosted_ui" {
  description = "Cognito hosted UI base URL of the staging access gate, null when the gate is off"
  value       = one(module.staging_access_gate[*].hosted_ui_domain)
}

output "staging_access_gate_user_pool_id" {
  description = "Cognito user pool id of the staging access gate, null when the gate is off"
  value       = one(module.staging_access_gate[*].user_pool_id)
}

output "github_actions_ci_role_arn" {
  description = "ARN of the read-only CodeArtifact role pull request CI assumes, set as the CI_AWS_ROLE_ARN repository variable"
  value       = module.github_actions_ci_role.role_arn
}

output "domain_lambda_function_names" {
  description = "Lambda function name keyed by domain, used to build the function-image map for UpdateFunctionCode"
  value       = { for name, fn in module.lambda_domain : name => fn.function_name }
}

output "domain_lambda_log_group_names" {
  description = "CloudWatch log group name keyed by domain, read by the error metric filters and by responders"
  value       = { for name, fn in module.lambda_domain : name => fn.log_group_name }
}
