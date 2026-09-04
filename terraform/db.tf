resource "aws_ssm_parameter" "secret_key" {
  name  = "/${local.prefix}/secret-key"
  type  = "SecureString"
  value = random_password.secret_key.result
}

resource "random_password" "secret_key" {
  length  = 64
  special = true
}

# Admin credentials seeded into the app on startup. Set values manually
# in SSM after first apply; Terraform ignores subsequent changes.
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
