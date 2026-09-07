# ---------------------------------------------------------------------------
# Application secrets.
#
# These four values live in SSM SecureString parameters today and are moving to
# Secrets Manager through the shared app-secrets module. The migration is staged
# so the running application is never pointed at a secret that has no value yet:
#
#   1. (this change) create the secrets and grant the Lambda role read access,
#      leaving the SSM parameters and their IAM grant in place.
#   2. copy the values across with scripts/migrate_secrets_to_secrets_manager.sh,
#      which pipes each value from SSM into Secrets Manager without it ever
#      reaching a terminal, a log or a file.
#   3. switch the backend to read Secrets Manager and repoint the Lambda
#      environment variables at the ARNs below.
#   4. delete the aws_ssm_parameter resources and the ssm:GetParameter grant.
#
# secret-key carries the generator itself: random_password.secret_key moves into
# the module rather than being replaced, so the existing signing key survives and
# live sessions are not invalidated.
#
# The three admin credentials stay operator-owned. They are seeded once with a
# placeholder and carry ignore_changes on the stored value, exactly as the SSM
# parameters do today, so Terraform never learns the real values and never plans
# them back. That is why they are three secrets rather than one JSON blob: the
# json shape would put every value in state, and ignore_changes cannot cover a
# subset of one blob.
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

# Load-bearing: without this Terraform destroys the generator and creates a new
# one, which regenerates the signing key and logs every session out.
moved {
  from = random_password.secret_key
  to   = module.app_secrets.random_password.this["secret-key"]
}

# ---------------------------------------------------------------------------
# The SSM SecureString parameters the backend still reads. They are removed in
# step 4, once the values are across and the application reads Secrets Manager.
# ---------------------------------------------------------------------------

# The generator moves into the module, which by design exposes no output holding
# a secret value, so this parameter can no longer be wired to it. It already
# holds the generated key and the backend still reads it until step 3, so it
# keeps its current value under ignore_changes and is deleted in step 4. The
# literal below is never applied over the live value.
resource "aws_ssm_parameter" "secret_key" {
  name  = "/${local.prefix}/secret-key"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "admin_username" {
  name  = "/${local.prefix}/admin-username"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "admin_password" {
  name  = "/${local.prefix}/admin-password"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "admin_email" {
  name  = "/${local.prefix}/admin-email"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}
