# ---------------------------------------------------------------------------
# The DynamoDB layer from the shared dynamodb-tables module. The table
# definitions stay here as locals, reshaped into the module's input: attributes
# as a list of objects, gsis as global_secondary_indexes, ttl as ttl_attribute
# and pitr as point_in_time_recovery. Nine of the ten tables had pitr = true,
# so that is the module wide value and only meta overrides it.
# ---------------------------------------------------------------------------

locals {
  dynamodb_entity_tables = ["users", "categories", "posts", "projects", "experience", "skills", "education", "certifications", "site-content"]

  dynamodb_tables = merge(
    {
      for entity in local.dynamodb_entity_tables : entity => {
        hash_key   = "id"
        attributes = [{ name = "id", type = "N" }]
      }
    },
    {
      posts = {
        hash_key = "id"
        attributes = [
          { name = "id", type = "N" },
          { name = "published_flag", type = "S" },
          { name = "published_at", type = "S" },
          { name = "category_id", type = "N" },
        ]
        global_secondary_indexes = [
          { name = "published-index", hash_key = "published_flag", range_key = "published_at", projection_type = "ALL" },
          { name = "category-index", hash_key = "category_id", range_key = "id", projection_type = "KEYS_ONLY" },
        ]
      }
      meta = {
        hash_key               = "pk"
        attributes             = [{ name = "pk", type = "S" }]
        ttl_attribute          = "ttl"
        point_in_time_recovery = false
      }
    },
  )
}

module "dynamodb" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/dynamodb-tables"
  version = "~> 1.6"

  name_prefix = local.prefix
  tables      = local.dynamodb_tables

  point_in_time_recovery = true
  deletion_protection    = var.environment == "production"
}

moved {
  from = aws_dynamodb_table.this["users"]
  to   = module.dynamodb.aws_dynamodb_table.this["users"]
}

moved {
  from = aws_dynamodb_table.this["categories"]
  to   = module.dynamodb.aws_dynamodb_table.this["categories"]
}

moved {
  from = aws_dynamodb_table.this["posts"]
  to   = module.dynamodb.aws_dynamodb_table.this["posts"]
}

moved {
  from = aws_dynamodb_table.this["projects"]
  to   = module.dynamodb.aws_dynamodb_table.this["projects"]
}

moved {
  from = aws_dynamodb_table.this["experience"]
  to   = module.dynamodb.aws_dynamodb_table.this["experience"]
}

moved {
  from = aws_dynamodb_table.this["skills"]
  to   = module.dynamodb.aws_dynamodb_table.this["skills"]
}

moved {
  from = aws_dynamodb_table.this["education"]
  to   = module.dynamodb.aws_dynamodb_table.this["education"]
}

moved {
  from = aws_dynamodb_table.this["certifications"]
  to   = module.dynamodb.aws_dynamodb_table.this["certifications"]
}

moved {
  from = aws_dynamodb_table.this["site-content"]
  to   = module.dynamodb.aws_dynamodb_table.this["site-content"]
}

moved {
  from = aws_dynamodb_table.this["meta"]
  to   = module.dynamodb.aws_dynamodb_table.this["meta"]
}
