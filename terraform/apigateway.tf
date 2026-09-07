# ---------------------------------------------------------------------------
# HTTP API in front of the Lambda backend.
#
# Behind the staging access gate the API is reachable only through its custom
# domain, where the origin-verify authorizer applies; both inputs are gated on
# local.staging_gate_enabled so production plans a no-op.
#
# The certificate lives in acm.tf and the api.<domain> alias record in
# route53.tf, because production writes DNS through aws.dns.
# ---------------------------------------------------------------------------

module "api" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/http-api"
  version = "~> 1.3"

  name = "${local.prefix}-api"

  lambda_invoke_arn    = aws_lambda_function.api.invoke_arn
  lambda_function_name = aws_lambda_function.api.function_name

  route_keys                     = ["ANY /{proxy+}", "ANY /"]
  throttling_burst_limit         = 200
  throttling_rate_limit          = 100
  access_log_retention_days      = 30
  lambda_permission_statement_id = "AllowAPIGatewayInvoke"

  access_log_format = {
    requestId               = "$context.requestId"
    ip                      = "$context.identity.sourceIp"
    requestTime             = "$context.requestTime"
    httpMethod              = "$context.httpMethod"
    routeKey                = "$context.routeKey"
    path                    = "$context.path"
    status                  = "$context.status"
    responseLength          = "$context.responseLength"
    integrationErrorMessage = "$context.integrationErrorMessage"
    integrationLatency      = "$context.integrationLatency"
  }

  disable_execute_api_endpoint = local.staging_gate_enabled
  authorizer_id                = local.staging_gate_enabled ? one(module.staging_access_gate[*].http_api_authorizer_id) : null

  domain_name     = local.custom_domains_enabled ? local.api_host : null
  certificate_arn = local.custom_domains_enabled ? aws_acm_certificate_validation.api[0].certificate_arn : null
  # zone_id stays null: production writes api.webbpulse.com cross-account through aws.dns.
}
