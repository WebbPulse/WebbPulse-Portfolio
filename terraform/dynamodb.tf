locals {
  dynamodb_entity_tables = ["users", "categories", "posts", "projects", "experience", "skills", "education", "certifications", "site-content"]

  dynamodb_tables = merge(
    {
      for entity in local.dynamodb_entity_tables : entity => {
        hash_key   = "id"
        attributes = { id = "N" }
        gsis       = []
        ttl        = null
        pitr       = true
      }
    },
    {
      posts = {
        hash_key   = "id"
        attributes = { id = "N", published_flag = "S", published_at = "S", category_id = "N" }
        gsis = [
          { name = "published-index", hash_key = "published_flag", range_key = "published_at", projection_type = "ALL" },
          { name = "category-index", hash_key = "category_id", range_key = "id", projection_type = "KEYS_ONLY" },
        ]
        ttl  = null
        pitr = true
      }
      meta = {
        hash_key   = "pk"
        attributes = { pk = "S" }
        gsis       = []
        ttl        = "ttl"
        pitr       = false
      }
    },
  )
}

resource "aws_dynamodb_table" "this" {
  for_each = local.dynamodb_tables

  name                        = "${local.prefix}-${each.key}"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = each.value.hash_key
  deletion_protection_enabled = var.environment == "production"

  dynamic "attribute" {
    for_each = each.value.attributes
    content {
      name = attribute.key
      type = attribute.value
    }
  }

  dynamic "global_secondary_index" {
    for_each = each.value.gsis
    content {
      name            = global_secondary_index.value.name
      hash_key        = global_secondary_index.value.hash_key
      range_key       = global_secondary_index.value.range_key
      projection_type = global_secondary_index.value.projection_type
    }
  }

  dynamic "ttl" {
    for_each = each.value.ttl == null ? [] : [each.value.ttl]
    content {
      attribute_name = ttl.value
      enabled        = true
    }
  }

  point_in_time_recovery {
    enabled = each.value.pitr
  }
}
