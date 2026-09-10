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
      # The login limiter's own table. Its items used to live in meta, which
      # made the id allocator share a table with a hot, high churn workload and
      # gave every writing domain a reason to hold write access to it. Keeping
      # them apart is what lets identity be the only domain that writes here.
      #
      # The TTL attribute is expires_at, not the ttl that meta uses. That is
      # the name webbpulse.ratelimit writes and app/db/tables.py mirrors as
      # RATE_LIMIT_TTL_ATTRIBUTE, so the declaration follows the package rather
      # than the neighbouring table. The two names have to stay distinct while
      # both tables exist.
      #
      # No point in time recovery: every item is a failure counter that expires
      # within LOGIN_FAILURE_WINDOW_SECONDS, so there is nothing here worth
      # restoring to a point in time.
      "rate-limits" = {
        hash_key               = "pk"
        attributes             = [{ name = "pk", type = "S" }]
        ttl_attribute          = "expires_at"
        point_in_time_recovery = false
      }

      # ---------------------------------------------------------------
      # The identity standard's four tables are NOT here any more.
      #
      # credentials, refresh-tokens, login-attempts and identity-tokens moved
      # into the platform identity module, which owns the whole identity layer:
      # the same four tables, the KMS signing key, and the two IAM grants the
      # identity function needs on both. terraform/identity.tf has the module
      # call and the `moved` blocks; the physical names are unchanged, because
      # both modules build "<name_prefix>-<key>" from the same local.prefix.
      #
      # The key schemas travelled with them rather than being restated: the
      # module's default `tables` map already carries the package's contract for
      # all four, byte identical to what this file declared. Only the point in
      # time recovery override on identity-tokens is repeated at the module
      # call, because the module's default leaves it null.
      # ---------------------------------------------------------------
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
