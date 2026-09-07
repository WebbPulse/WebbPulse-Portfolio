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

  # AWS/Lambda Errors only counts an invocation that raised. A request the
  # function handled but logged an error for, a caught failure from a
  # downstream call or a rejected payload, is invisible to it and exists only
  # in the logs. This adds one metric filter over the API log group and one
  # "<prefix>-application-errors" alarm on the metric it publishes.
  #
  # The key is the domain the function serves, because it is what a responder
  # reads in the filter name. The log group comes from the module output so it
  # cannot drift from the function it belongs to. error_filter_pattern keeps
  # its default of { $.level = "ERROR" }, which matches what Powertools writes
  # once lambda.tf sets log_format = "JSON".
  error_log_groups = {
    api = module.lambda_api.log_group_name
  }
}
