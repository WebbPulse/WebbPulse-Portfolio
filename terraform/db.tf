# ---------------------------------------------------------------------------
# Application secrets, held in Secrets Manager through the shared app-secrets
# module. They were SSM SecureString parameters until the values were copied
# across and the backend switched over; the parameters and their IAM grant are
# gone.
#
# The estate is moving to one secret per service per environment: webbpulse-<env>/app,
# a single JSON object the Lambda reads once at cold start through APP_SECRETS_ARN.
# This change adds that secret alongside the four per-key secrets it replaces. The
# old four stay until the backend reads the new one, so a rollback is a redeploy
# rather than a restore; a later change removes them.
#
# The signing key is not a variable. random_password.secret_key generates it and
# keeps generating the same value, so the key that has been signing sessions
# since before any of this survives and nobody is logged out. It moves back out
# of the module here because the module's generated value can only reach its own
# secret, and the JSON blob needs it too.
#
# The three admin credentials become sensitive workspace variables. They were
# placeholders populated out of band, which was the right shape while Terraform
# had to stay ignorant of them, but a JSON blob cannot carry ignore_changes on a
# subset of its keys. A sensitive variable keeps them out of the plan text and
# out of every log, and puts the values where an operator can rotate them.
# ---------------------------------------------------------------------------

# Arguments match the module's random_password exactly, so moving the generator
# out of the module changes no attribute and regenerates nothing.
resource "random_password" "secret_key" {
  length           = 64
  special          = true
  override_special = null
  min_special      = 0
  min_numeric      = 0
  min_upper        = 0
  min_lower        = 0
}

# Load-bearing: without this Terraform destroys the generator and creates a new
# one, which regenerates the signing key and logs every session out.
moved {
  from = module.app_secrets.random_password.this["secret-key"]
  to   = random_password.secret_key
}

module "app_secrets" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/app-secrets"
  version = "~> 1.6"

  name_prefix = local.prefix

  secrets = {
    # The one secret the backend reads. Its keys are the setting names the
    # application already uses, so there is no mapping to keep in step.
    "app" = {
      description = "JSON map of runtime secrets read by the Lambda API at cold start"
      json = {
        SECRET_KEY     = random_password.secret_key.result
        ADMIN_USERNAME = var.admin_username
        ADMIN_PASSWORD = var.admin_password
        ADMIN_EMAIL    = var.admin_email
      }
    }

    # Superseded by "app" above. Kept until the backend reads the JSON blob, then
    # removed. The value stays as it is: secret-key no longer generates here, it
    # takes the same generator's result, so the stored string does not change.
    "secret-key" = {
      description = "JWT signing key for the FastAPI backend. Superseded by the app secret."
      value       = random_password.secret_key.result
    }

    # Admin credentials seeded into the app on startup. Superseded by "app" above
    # and removed once the backend reads it. They keep their placeholder shape so
    # this change does not plan over the values an operator set out of band.
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
