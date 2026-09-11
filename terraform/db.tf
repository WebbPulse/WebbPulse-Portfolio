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
    "app" = {
      description = "JSON map of runtime secrets read by the Lambda API at cold start"
      json = {
        SECRET_KEY     = random_password.secret_key.result
        ADMIN_USERNAME = var.admin_username
        ADMIN_PASSWORD = var.admin_password
        ADMIN_EMAIL    = var.admin_email

        OAUTH_GOOGLE_CLIENT_SECRET = var.oauth_google_client_secret
        OAUTH_GITHUB_CLIENT_SECRET = var.oauth_github_client_secret
      }
    }
  }
}
