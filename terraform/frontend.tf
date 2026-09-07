# ---------------------------------------------------------------------------
# Frontend — private S3 bucket served via CloudFront, from the shared
# spa-frontend module.
#
# The apex and www hostnames both point at this distribution.
# A CloudFront Function 301-redirects the bare apex to www.
# 403/404 from S3 → index.html for client-side React Router.
#
# The frontend calls the API host directly, on every environment, so there is
# no proxying through CloudFront. The staging access gate adds only the sign-in
# wall: /_auth/* goes to the gate's login Lambda and the page behaviors require
# the gate's signed cookies. The API host checks the same cookies itself, in
# its own authorizer. The access_gate object is null unless
# local.staging_gate_enabled, so production plans a no-op.
#
# The Route 53 alias records stay in route53.tf: production writes them
# cross-account through aws.dns and a module has one aws provider. The ACM
# certificate stays in acm.tf for the same reason.
# ---------------------------------------------------------------------------

module "frontend" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/spa-frontend"
  version = "~> 1.1"

  name = "${local.prefix}-frontend" # bucket and OAC webbpulse-<env>-frontend
  # origin_id = "s3-frontend" and bucket_policy_sid = "AllowCloudFrontServicePrincipal" are the defaults.

  aliases             = local.custom_domains_enabled ? [local.www_host, local.domain] : []
  acm_certificate_arn = one(aws_acm_certificate_validation.www[*].certificate_arn)

  viewer_request_function_arn = one(aws_cloudfront_function.apex_redirect[*].arn)

  cache_mode = "forwarded_values"
  # forwarded_values defaults: query_string false, cookies none, TTLs 0 / 86400 / 31536000.
  error_caching_min_ttl = 10

  # The live distribution mixes the two cache models: the default behavior kept its legacy
  # forwarded_values block, while the /index.html behavior was added later with the managed
  # CachingOptimized policy and nothing else. These two inputs reproduce that exactly.
  index_cache_mode     = "policies"
  index_cache_policies = { cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6" }

  # Staging access gate, direct subdomain shape: the login origin, /_auth/*, the unsigned
  # /index.html behavior and the key group on the default behavior. No API origin and no /api/*
  # behavior, so no origin verification header value is needed here. login_origin_id is left at
  # the module default of "access-gate-login", which is the origin id the hand-written
  # distribution used.
  access_gate = local.staging_gate_enabled ? {
    key_group_id                                           = module.staging_access_gate[0].key_group_id
    viewer_request_function_arn                            = module.staging_access_gate[0].viewer_request_function_arn
    login_origin_domain_name                               = module.staging_access_gate[0].login_origin_domain_name
    login_origin_access_control_id                         = module.staging_access_gate[0].login_origin_access_control_id
    auth_path_pattern                                      = module.staging_access_gate[0].auth_path_pattern
    cache_policy_id_caching_disabled                       = module.staging_access_gate[0].cache_policy_id_caching_disabled
    origin_request_policy_id_all_viewer_except_host_header = module.staging_access_gate[0].origin_request_policy_id_all_viewer_except_host_header
  } : null

  # The alias records live in route53.tf, on the aws.dns provider.
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
