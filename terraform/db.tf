removed {
  from = random_password.secret_key

  lifecycle {
    destroy = false
  }
}

module "app_secrets" {
  source  = "terraform.webbpulse.com/WebbPulse/platform-modules/aws//modules/app-secrets"
  version = "~> 2.39"

  name_prefix = local.prefix

  secrets = {
    "app" = {
      description             = "JSON map of runtime secrets read by the Lambda API at cold start"
      version                 = 2
      json_preserve_unmanaged = true
      json_generate = {
        SECRET_KEY = {
          format = "password"
          keep   = true
          length = 64
        }
        mfa_master_key = {
          format = "bytes32-base64"
          keep   = true
        }
      }
    }
  }
}
