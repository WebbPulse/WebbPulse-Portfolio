module "registry" {
  source  = "terraform.webbpulse.com/WebbPulse/platform-modules/aws//modules/ecr-repository"
  version = "~> 2.39"

  name_prefix = local.prefix

  keep_last_tagged_images = 3

  repositories = {
    content  = { force_delete = true }
    resume   = { force_delete = true }
    identity = { force_delete = true }
    public   = {}
  }
}
