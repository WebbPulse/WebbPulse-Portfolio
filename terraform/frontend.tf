# ---------------------------------------------------------------------------
# Frontend — private S3 bucket served via CloudFront, from the shared
# spa-frontend module.
#
# The apex and www hostnames both point at this distribution.
# A CloudFront Function 301-redirects the bare apex to www.
# 403/404 from S3 → index.html for client-side React Router.
#
# The frontend calls the API host directly — there is no proxying through
# CloudFront. The one exception is the staging access gate: when it is on,
# /api/* is proxied to the API host with an origin-verify header, /_auth/* goes
# to the gate's login Lambda, and every behavior requires signed cookies. The
# module does all of that from the access_gate object below, which is null in
# production so the distribution plans a plain site.
#
# The www and apex alias records stay in route53.tf: production writes them
# cross-account through aws.dns, and a module has one aws provider.
# ---------------------------------------------------------------------------

module "frontend" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/spa-frontend"
  version = "~> 1.3"

  name = "${local.prefix}-frontend"
  # origin_id "s3-frontend" and bucket_policy_sid "AllowCloudFrontServicePrincipal" are the defaults.

  aliases             = local.custom_domains_enabled ? [local.www_host, local.domain] : []
  acm_certificate_arn = one(aws_acm_certificate_validation.www[*].certificate_arn)

  viewer_request_function_arn = one(aws_cloudfront_function.apex_redirect[*].arn)

  cache_mode = "forwarded_values"
  forwarded_values = {
    query_string    = false
    cookies_forward = "none"
    min_ttl         = 0
    default_ttl     = 86400
    max_ttl         = 31536000
  }
  error_caching_min_ttl = 10

  access_gate = local.staging_gate_enabled ? {
    key_group_id                                           = module.staging_access_gate[0].key_group_id
    viewer_request_function_arn                            = module.staging_access_gate[0].viewer_request_function_arn
    login_origin_domain_name                               = module.staging_access_gate[0].login_origin_domain_name
    login_origin_access_control_id                         = module.staging_access_gate[0].login_origin_access_control_id
    auth_path_pattern                                      = module.staging_access_gate[0].auth_path_pattern
    api_origin_domain_name                                 = local.api_host
    api_path_pattern                                       = module.staging_access_gate[0].api_path_pattern
    origin_verify_header_name                              = module.staging_access_gate[0].origin_verify_header_name
    origin_verify_header_value                             = module.staging_access_gate[0].origin_verify_header_value
    cache_policy_id_caching_disabled                       = module.staging_access_gate[0].cache_policy_id_caching_disabled
    origin_request_policy_id_all_viewer_except_host_header = module.staging_access_gate[0].origin_request_policy_id_all_viewer_except_host_header
  } : null

  create_dns_records = false
}

# Apex to www redirect. The logic lives in cloudfront_functions/app_handler.js.tftpl
# so the staging access gate can run the same appHandler before its own check;
# without the gate this function wraps it directly as the viewer-request handler.
resource "aws_cloudfront_function" "apex_redirect" {
  count = local.custom_domain_count

  name    = "${local.prefix}-apex-redirect"
  runtime = "cloudfront-js-2.0"
  publish = true

  code = join("\n", [
    templatefile("${path.module}/cloudfront_functions/app_handler.js.tftpl", {
      domain   = local.domain
      www_host = local.www_host
    }),
    "async function handler(event) { return appHandler(event); }",
  ])
}
