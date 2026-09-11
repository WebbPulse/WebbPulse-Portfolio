module "registry" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/ecr-repository"
  version = "~> 2.0"

  name_prefix = local.prefix

  repositories = {
    content  = {}
    resume   = {}
    identity = {}
    public   = {}
  }
}
