# ---------------------------------------------------------------------------
# CloudWatch alarms for the Lambda backed HTTP API, from the shared api-alarms
# module: one SNS topic with the two email subscribers, aggregate Lambda errors
# and throttles across the whole function estate, HTTP API 5xx and p99
# integration latency, and one aggregate read plus write throttle alarm
# covering every DynamoDB table.
#
# Applying it emails each address a subscription confirmation link, and no
# alarm delivers to an address until that link is clicked. Every threshold,
# period and evaluation count keeps the module default, which is what
# CarModPicker runs.
# ---------------------------------------------------------------------------

module "alarms" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/api-alarms"
  version = "~> 2.4"

  name_prefix         = local.prefix
  notification_emails = ["tyler@webbpulse.com", "tylert2610@gmail.com"]

  http_api_id = module.api.api_id

  # The many function form. lambda_function_name stays unset, because the module
  # accepts one of the two forms and rejects a plan that sets both, and because
  # a pair of alarms per function across four functions is eight alarms and
  # eight billable alarm metrics for one signal. These are two metric math
  # alarms, "<prefix>-lambda-errors-aggregate" and
  # "<prefix>-lambda-throttles-aggregate", each a SUM over one AWS/Lambda metric
  # per name below. A fifth domain changes the expression on the existing alarms
  # rather than adding another pair.
  #
  # The monolith used to lead this list and is gone with the retirement, so the
  # four domains are now the whole of it. That is a change to both alarms and
  # not only a shorter list: the module turns the list into positional metric
  # math ids, m0, m1 and so on, so dropping the head shifts every domain's id
  # down one and rewrites both alarm definitions. It is a metric math rewrite
  # with no behaviour change, and it is the one item on the retirement plan that
  # is a change rather than a destroy.
  #
  # Order still matters for the same reason. Appending a new function is the
  # cheap edit; inserting one in the middle is not.
  lambda_function_names = [
    for name in keys(local.lambda_domains) : module.lambda_domain[name].function_name
  ]
  lambda_aggregate_alarm = true

  # Held at the module default of 0 with GreaterThanThreshold, the same value
  # the per-function alarm carried before this change, so any single error or
  # throttle on any of the four functions alarms. That is a starting point and
  # not a settled answer: four functions summed will trip more often than one
  # did, and staging and production may want different numbers. The threshold is
  # the open alarm question in section 9 of docs/migration/pilot-split-plan.md
  # and is left for a per-environment judgement.
  lambda_aggregate_threshold = 0

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
  # in the logs. This adds one metric filter per log group and one
  # "<prefix>-application-errors" alarm on the shared metric they publish.
  #
  # Every filter writes that one dimensionless metric, so four log groups still
  # means exactly one alarm, and this is the shape that keeps scaling past the
  # ten metric ceiling the aggregate alarms above sit under.
  #
  # The key is the domain the function serves, because it is what a responder
  # reads in the filter name. The "api" key was the monolith's and goes with it,
  # which destroys that one metric filter and leaves the four domain filters at
  # their own keys untouched. The log groups come from the module outputs so
  # they cannot drift from the functions they belong to. error_filter_pattern
  # keeps its default of { $.level = "ERROR" }, which matches what the domain
  # functions write under log_format = "JSON".
  error_log_groups = {
    for name in keys(local.lambda_domains) : name => module.lambda_domain[name].log_group_name
  }

  # The login limiter in app/core/login_limiter.py allows a request when it
  # cannot reach "<prefix>-rate-limits", rather than refusing it, because
  # refusing every login while DynamoDB is unavailable turns a dependency blip
  # into a full outage. Nothing reported that: the request succeeded, so
  # AWS/Lambda Errors stays at zero and the API returns 200 while the login
  # limit is not being enforced. This is one metric filter and one
  # "<prefix>-rate-limit-failed-open" alarm on the metric it publishes.
  rate_limit_fail_open_alarm = true

  # Scoped to identity, not defaulted to error_log_groups. The limiter is called
  # from the identity router's login path only, not from global middleware, and
  # identity is the one domain granted the rate-limits table above. A filter on
  # the other three would watch a log group that can never emit the record, and
  # would read as though those functions were covered.
  rate_limit_fail_open_log_groups = {
    identity = module.lambda_domain["identity"].log_group_name
  }

  # rate_limit_fail_open_filter_pattern keeps its module default of
  # { $.rate_limit_failed_open IS TRUE }, which matches a top level JSON field.
  # That holds here: _failed_open passes the flag as a keyword to the Powertools
  # logger, which writes it as its own field rather than into the message text,
  # and the domain functions run with log_format = "JSON". CarModPicker's
  # limiter interpolates the flag into the message instead and has to override
  # the pattern; this one does not.
}
