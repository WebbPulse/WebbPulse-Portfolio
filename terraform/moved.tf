# Historical count moves. Terraform follows the chain into the module moves below.
moved {
  from = aws_route53_record.api
  to   = aws_route53_record.api[0]
}

moved {
  from = aws_route53_record.www
  to   = aws_route53_record.www[0]
}

moved {
  from = aws_route53_record.apex_a
  to   = aws_route53_record.apex_a[0]
}

moved {
  from = aws_acm_certificate.www
  to   = aws_acm_certificate.www[0]
}

moved {
  from = aws_acm_certificate_validation.www
  to   = aws_acm_certificate_validation.www[0]
}

moved {
  from = aws_cloudfront_function.apex_redirect
  to   = aws_cloudfront_function.apex_redirect[0]
}

# ---------------------------------------------------------------------------
# Adoption of the shared platform modules. State moves only.
# ---------------------------------------------------------------------------

# staging-dns
moved {
  from = aws_route53_zone.staging[0]
  to   = module.staging_dns.aws_route53_zone.this[0]
}

moved {
  from = aws_route53_record.staging_delegation[0]
  to   = module.staging_dns.aws_route53_record.delegation[0]
}

# http-api
moved {
  from = aws_apigatewayv2_api.backend
  to   = module.api.aws_apigatewayv2_api.this
}

moved {
  from = aws_cloudwatch_log_group.apigateway_access
  to   = module.api.aws_cloudwatch_log_group.access
}

moved {
  from = aws_apigatewayv2_integration.lambda
  to   = module.api.aws_apigatewayv2_integration.lambda
}

moved {
  from = aws_apigatewayv2_route.proxy
  to   = module.api.aws_apigatewayv2_route.this["ANY /{proxy+}"]
}

moved {
  from = aws_apigatewayv2_route.root
  to   = module.api.aws_apigatewayv2_route.this["ANY /"]
}

moved {
  from = aws_apigatewayv2_stage.default
  to   = module.api.aws_apigatewayv2_stage.default
}

moved {
  from = aws_lambda_permission.apigateway
  to   = module.api.aws_lambda_permission.api
}

moved {
  from = aws_apigatewayv2_domain_name.api
  to   = module.api.aws_apigatewayv2_domain_name.this
}

moved {
  from = aws_apigatewayv2_api_mapping.api
  to   = module.api.aws_apigatewayv2_api_mapping.this
}

# spa-frontend
moved {
  from = aws_s3_bucket.frontend
  to   = module.frontend.aws_s3_bucket.this
}

moved {
  from = aws_s3_bucket_public_access_block.frontend
  to   = module.frontend.aws_s3_bucket_public_access_block.this
}

moved {
  from = aws_s3_bucket_policy.frontend
  to   = module.frontend.aws_s3_bucket_policy.this
}

moved {
  from = aws_cloudfront_origin_access_control.frontend
  to   = module.frontend.aws_cloudfront_origin_access_control.this
}

moved {
  from = aws_cloudfront_distribution.frontend
  to   = module.frontend.aws_cloudfront_distribution.this
}
