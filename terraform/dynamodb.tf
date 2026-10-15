locals {
  dynamodb_tables = {
    "public-cache" = {
      hash_key               = "pk"
      attributes             = [{ name = "pk", type = "S" }]
      ttl_attribute          = "ttl"
      point_in_time_recovery = false
      deletion_protection    = var.environment == "production"
    }
  }
}

module "dynamodb" {
  source  = "terraform.webbpulse.com/WebbPulse/platform-modules/aws//modules/dynamodb-tables"
  version = "~> 2.39"

  name_prefix = local.prefix
  tables      = local.dynamodb_tables

  point_in_time_recovery = true
  deletion_protection    = false
}
