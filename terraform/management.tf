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

# ---------------------------------------------------------------------------
# Tag Sync — fill permission gaps on the AWS-managed tag-sync role.
#
# Enabling tag-sync on a myApplications application (via the console) creates
# a service role named `tag-sync-role-<region>-<random-suffix>` with only the
# AWS-managed `ResourceGroupsTaggingAPITagUntagSupportedResources` policy
# attached. That policy omits App Runner and Service Catalog AppRegistry, so
# the sync fails with AccessDenied when it tries to apply the
# `awsApplication` tag to those resource types (surfaces in the "Resource
# tagging error status" panel). This policy closes that gap.
#
# The tag-sync role + task themselves are not managed by Terraform — the AWS
# provider has no resource type for tag-sync tasks. We look up the role by
# regex so a console disable/re-enable (which regenerates the suffix) doesn't
# break the next apply. If tag-sync is disabled, the data source returns an
# empty set and the for_each attaches nothing — safe either way.
# ---------------------------------------------------------------------------
data "aws_iam_roles" "tag_sync" {
  name_regex  = "^tag-sync-role-${var.aws_region}-"
  path_prefix = "/service-role/"
}

resource "aws_iam_policy" "tag_sync_extras" {
  name        = "${local.prefix}-tag-sync-extras"
  description = "Extra tag permissions for myApplications tag-sync (fills gaps in the AWS managed tag-sync policy)"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "apprunner:TagResource",
        "apprunner:UntagResource",
        "apprunner:ListTagsForResource",
        "servicecatalog:TagResource",
        "servicecatalog:UntagResource",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "tag_sync_extras" {
  for_each   = data.aws_iam_roles.tag_sync.names
  role       = each.value
  policy_arn = aws_iam_policy.tag_sync_extras.arn
}
