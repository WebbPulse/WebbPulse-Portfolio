# ---------------------------------------------------------------------------
# CloudWatch alarms for the Lambda backed HTTP API, from the shared api-alarms
# module: one SNS topic with the two email subscribers, Lambda errors and
# throttles, HTTP API 5xx and p99 integration latency, and a read plus write
# throttle alarm per DynamoDB table.
#
# This is new for WebbPulse-Portfolio, so the whole set is an add. Applying it
# emails each address a subscription confirmation link, and no alarm delivers
# to an address until that link is clicked. Every threshold, period and
# evaluation count keeps the module default, which is what CarModPicker runs.
# ---------------------------------------------------------------------------

module "alarms" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/api-alarms"
  version = "~> 1.6"

  name_prefix         = local.prefix
  notification_emails = ["tyler@webbpulse.com", "tylert2610@gmail.com"]

  lambda_function_name = module.lambda_api.function_name
  http_api_id          = module.api.api_id

  # Keyed by the entity key the tables are defined under, so each alarm's
  # address is stable; the value is the real table name, which is what
  # "<table name>-throttles" is built from.
  dynamodb_tables = module.dynamodb.table_names
}
