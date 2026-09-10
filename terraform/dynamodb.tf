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
      # The identity standard's M2 tables. Section 4.1 of
      # docs/identity-standard.md fixes every key name, index name and TTL
      # attribute below, and webbpulse.identity.storage reads and writes
      # exactly these names. They are copied rather than derived, so a
      # mismatch is a failing test here rather than a ValidationException
      # at 3am, and each one is checked by tests/test_identity_m2.py
      # against the constants the package exports.
      # ---------------------------------------------------------------

      # The password hash, kept off the user record on purpose: a route that
      # returns a user cannot accidentally serialise a hash when the hash
      # lives in another table. Hash user_id, range credential_type, so a
      # second credential kind can exist later without another column on
      # users.
      #
      # No TTL, ever. A credential expiring on a storage reclaim schedule
      # would sign somebody out of their own account, and DynamoDB deletes
      # on its own timetable rather than on the deadline.
      credentials = {
        hash_key  = "user_id"
        range_key = "credential_type"
        attributes = [
          { name = "user_id", type = "S" },
          { name = "credential_type", type = "S" },
        ]
      }

      # One item per generation of one refresh family. Keyed on the SHA-256
      # of the token rather than on a token id, which makes the hot path,
      # "is this presented token valid", a single GetItem on the primary key
      # with no index in the way.
      #
      # family_id-generation-index exists for the other operation, revoking a
      # whole family after a reuse is detected, and is never on the
      # verification path. The name is the package's REFRESH_FAMILY_INDEX
      # constant and DynamoDB resolves an index by name, so the two cannot
      # differ.
      #
      # TTL expires_at reclaims storage only. The package checks every
      # deadline on read as well, because an expired item survives its
      # expiry by up to a couple of days.
      "refresh-tokens" = {
        hash_key = "token_hash"
        attributes = [
          { name = "token_hash", type = "S" },
          { name = "family_id", type = "S" },
          { name = "generation", type = "N" },
        ]
        global_secondary_indexes = [
          { name = "family_id-generation-index", hash_key = "family_id", range_key = "generation", projection_type = "ALL" },
        ]
        ttl_attribute = "expires_at"
      }

      # The progressive lockout's evidence. Hash identity_key, which is
      # `email#<lower>` or `ip#<addr>`, range attempted_at, so an attempt is
      # an append and never an overwrite and the history is readable newest
      # first without scanning every attempt ever made.
      #
      # No point in time recovery: a row is a failed login from the last 30
      # days, the lockout window is 24 hours, and there is nothing here worth
      # restoring to a point in time.
      "login-attempts" = {
        hash_key  = "identity_key"
        range_key = "attempted_at"
        attributes = [
          { name = "identity_key", type = "S" },
          { name = "attempted_at", type = "S" },
        ]
        ttl_attribute          = "expires_at"
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
