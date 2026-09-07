# ---------------------------------------------------------------------------
# Account housekeeping from the shared app-baseline module: the tag based
# resource group, Cost Explorer anomaly detection and the two free budgets.
# ---------------------------------------------------------------------------

module "app_baseline" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/app-baseline"
  version = "~> 1.6"

  name                = local.prefix
  notification_emails = ["tyler@webbpulse.com", "tylert2610@gmail.com"]

  resource_group_description = "All WebbPulse managed resources"
  resource_group_tag_filters = {
    Project = [local.project]
  }

  budgets = {
    "monthly-warn"     = { limit_amount = "10" }
    "monthly-critical" = { limit_amount = "25" }
  }
}

moved {
  from = aws_resourcegroups_group.webbpulse
  to   = module.app_baseline.aws_resourcegroups_group.this[0]
}

moved {
  from = aws_ce_anomaly_monitor.webbpulse
  to   = module.app_baseline.aws_ce_anomaly_monitor.this[0]
}

moved {
  from = aws_ce_anomaly_subscription.webbpulse
  to   = module.app_baseline.aws_ce_anomaly_subscription.this[0]
}

moved {
  from = aws_budgets_budget.warn
  to   = module.app_baseline.aws_budgets_budget.this["monthly-warn"]
}

moved {
  from = aws_budgets_budget.critical
  to   = module.app_baseline.aws_budgets_budget.this["monthly-critical"]
}
