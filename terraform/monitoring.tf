module "alarms" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/api-alarms"
  version = "~> 2.14"

  name_prefix         = local.prefix
  notification_emails = ["tyler@webbpulse.com", "tylert2610@gmail.com"]

  http_api_id = module.api.api_id

  lambda_function_names = [
    for name in keys(local.lambda_domains) : module.lambda_domain[name].function_name
  ]
  lambda_aggregate_alarm = true

  lambda_aggregate_threshold = 0

  dynamodb_aggregate_alarm = true
  dynamodb_tables          = {}

  error_log_groups = {
    for name in keys(local.lambda_domains) : name => module.lambda_domain[name].log_group_name
  }

  rate_limit_fail_open_alarm = true

  rate_limit_fail_open_log_groups = {
    identity = module.lambda_domain["identity"].log_group_name
  }

}
