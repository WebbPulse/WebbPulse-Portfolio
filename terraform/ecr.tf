module "registry" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/ecr-repository"
  version = "~> 2.0"

  name_prefix = local.prefix

  keep_last_tagged_images = 3

  repositories = {
    content  = {}
    resume   = {}
    identity = {}
    public   = {}
  }
}
