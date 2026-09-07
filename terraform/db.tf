# ---------------------------------------------------------------------------
# Application secrets, held in Secrets Manager through the shared app-secrets
# module. They were SSM SecureString parameters until the values were copied
# across and the backend switched over; the parameters and their IAM grant are
# gone.
#
# secret-key carries the generator itself: random_password.secret_key lives in
# the module, so the signing key that was generated before the move survives and
# live sessions were never invalidated.
#
# The three admin credentials stay operator-owned. They are seeded once with a
# placeholder and carry ignore_changes on the stored value, so Terraform never
# learns the real values and never plans them back. That is why they are three
# secrets rather than one JSON blob: the json shape would put every value in
# state, and ignore_changes cannot cover a subset of one blob.
# ---------------------------------------------------------------------------

module "app_secrets" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/app-secrets"
  version = "~> 1.6"

  name_prefix = local.prefix

  secrets = {
    "secret-key" = {
      description     = "JWT signing key for the FastAPI backend"
      generate        = true
      generate_length = 64
    }

    # Admin credentials seeded into the app on startup. Set the values manually
    # in Secrets Manager after first apply; Terraform ignores later changes.
    "admin-username" = {
      description = "Username of the seeded admin user. Populated out of band with put-secret-value."
      placeholder = "REPLACE_ME"
    }

    "admin-password" = {
      description = "Password of the seeded admin user. Populated out of band with put-secret-value."
      placeholder = "REPLACE_ME"
    }

    "admin-email" = {
      description = "Email address of the seeded admin user. Populated out of band with put-secret-value."
      placeholder = "REPLACE_ME"
    }
  }
}
