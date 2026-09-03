# ---------------------------------------------------------------------------
# Resource Group — tag-based auto-discovery
# Surfaces all Project=webbpulse resources in the console.
# ---------------------------------------------------------------------------
resource "aws_resourcegroups_group" "webbpulse" {
  name        = local.prefix
  description = "All WebbPulse managed resources"

  resource_query {
    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters = [
        {
          Key    = "Project"
          Values = ["webbpulse"]
        }
      ]
    })
  }
}

# ---------------------------------------------------------------------------
# Cost Anomaly Detection — alerts on unexpected spend spikes (free)
# Monitors per AWS service; daily digest when any anomaly >= $10.
# ---------------------------------------------------------------------------
resource "aws_ce_anomaly_monitor" "webbpulse" {
  name              = local.prefix
  monitor_type      = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

resource "aws_ce_anomaly_subscription" "webbpulse" {
  name      = local.prefix
  frequency = "DAILY"

  monitor_arn_list = [aws_ce_anomaly_monitor.webbpulse.arn]

  subscriber {
    type    = "EMAIL"
    address = "tyler@webbpulse.com"
  }

  subscriber {
    type    = "EMAIL"
    address = "tylert2610@gmail.com"
  }

  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      match_options = ["GREATER_THAN_OR_EQUAL"]
      values        = ["10"]
    }
  }
}

# ---------------------------------------------------------------------------
# Budget alerts — first 2 budgets per account are free
# ---------------------------------------------------------------------------
resource "aws_budgets_budget" "warn" {
  name         = "${local.prefix}-monthly-warn"
  budget_type  = "COST"
  limit_amount = "10"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["tyler@webbpulse.com", "tylert2610@gmail.com"]
  }
}

resource "aws_budgets_budget" "critical" {
  name         = "${local.prefix}-monthly-critical"
  budget_type  = "COST"
  limit_amount = "25"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["tyler@webbpulse.com", "tylert2610@gmail.com"]
  }
}
