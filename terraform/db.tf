# ---------------------------------------------------------------------------
# Application secrets, held in Secrets Manager through the shared app-secrets
# module. One secret per service per environment: webbpulse-<env>/app, a single
# JSON object the Lambda reads once at cold start through APP_SECRETS_ARN.
#
# It replaced four per-key secrets, webbpulse-<env>/{secret-key,admin-username,
# admin-password,admin-email}, which were kept alongside it until the backend
# was reading the blob in both environments. This change deletes them.
#
# The signing key is not a variable. random_password.secret_key generates it and
# keeps generating the same value, so the key that has been signing sessions
# since before any of this is still the one in use. It lives outside the module
# because a value generated inside it can only reach its own secret, and the
# JSON blob needs it.
#
# The three admin credentials are sensitive workspace variables. They were
# placeholders populated out of band, which was the right shape while Terraform
# had to stay ignorant of them, but a JSON blob cannot carry ignore_changes on a
# subset of its keys. A sensitive variable keeps them out of the plan text and
# out of every log, and puts the values where an operator can rotate them.
# ---------------------------------------------------------------------------

# The generator holds the live signing key, so do not change these arguments and
# do not replace this resource: a new value logs every session out. The explicit
# defaults are the app-secrets module's own, from when the generator lived inside
# it, and are spelled out so nobody tidies them into a difference.
resource "random_password" "secret_key" {
  length           = 64
  special          = true
  override_special = null
  min_special      = 0
  min_numeric      = 0
  min_upper        = 0
  min_lower        = 0
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
  }
}
