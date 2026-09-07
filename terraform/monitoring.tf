# ---------------------------------------------------------------------------
# CloudWatch alarms for the Lambda backed HTTP API, from the shared api-alarms
# module: one SNS topic with the two email subscribers, Lambda errors and
# throttles, HTTP API 5xx and p99 integration latency, and one aggregate read
# plus write throttle alarm covering every DynamoDB table.
#
# Applying it emails each address a subscription confirmation link, and no
# alarm delivers to an address until that link is clicked. Every threshold,
# period and evaluation count keeps the module default, which is what
# CarModPicker runs.
# ---------------------------------------------------------------------------

module "alarms" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/api-alarms"
  version = "~> 1.7"

  name_prefix         = local.prefix
  notification_emails = ["tyler@webbpulse.com", "tylert2610@gmail.com"]

  lambda_function_name = module.lambda_api.function_name
  http_api_id          = module.api.api_id

  # One "<prefix>-dynamodb-throttles" alarm covering read and write throttling
  # across every table in the environment, instead of one alarm per table. With
  # 10 tables the per-table shape was 10 alarms and 20 billable alarm metrics;
  # this is one alarm that also picks up new tables without a Terraform change.
  # dynamodb_tables stays empty because the aggregate alarm needs no list.
  dynamodb_aggregate_alarm = true
  dynamodb_tables          = {}
}
