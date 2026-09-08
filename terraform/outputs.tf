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
  description = "CloudFront distribution ID — used by CI/CD to invalidate cache after deploys"
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
  description = "Base URL the frontend build must call (the API_BASE_URL GitHub environment variable). Always the API host; behind the staging access gate the browser sends the gate's signed cookies to it directly."
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

# The monolith's `lambda_function_name` output is gone with the function. The
# deploy job that read it through vars.LAMBDA_FUNCTION_NAME is gone too; the
# four domain functions are named by `domain_lambda_function_names` below.

output "lambda_artifact_bucket" {
  description = "S3 bucket the monolith's deployment zips were uploaded to. Kept after the monolith was retired because the last zip is what a rollback would restore the function from; nothing writes to it now."
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
  description = "ARN of the read-only CodeArtifact role pull request CI assumes. Set it as the CI_AWS_ROLE_ARN repository variable (staging value only, since pull request checks run against staging)."
  value       = module.github_actions_ci_role.role_arn
}

output "domain_lambda_function_names" {
  description = "Per-domain Lambda function name keyed by domain, for the function-image map the image deploy step passes to UpdateFunctionCode. Since the monolith was retired these are every Lambda the API routes to."
  value       = { for name, fn in module.lambda_domain : name => fn.function_name }
}

output "domain_lambda_log_group_names" {
  description = "Per-domain CloudWatch log group name keyed by domain. The application errors metric filters read it, and a responder tailing one domain does not have to guess the group from the function name."
  value       = { for name, fn in module.lambda_domain : name => fn.log_group_name }
}
