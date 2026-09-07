# ---------------------------------------------------------------------------
# Container registries for the per-domain FastAPI Lambdas, one repository per
# domain per environment. The names come out as "webbpulse-<env>/<domain>", so
# a slash namespaces every repository of one environment together in the
# console and a lifecycle rule that keeps the last ten tagged images means the
# last ten builds of that one domain.
#
# The functions that pull these images are created by this same root, in this
# same account and region, so no repository policy is written. Same-account
# access needs only one side to grant it, and Lambda writes its own
# LambdaECRImageRetrievalPolicy statement onto the repository at
# CreateFunction. Setting repository_policy_principals would make Terraform own
# the whole document and drop that statement on the next apply, which is the
# failure that only shows up when Lambda later re-fetches the image.
# ---------------------------------------------------------------------------

module "registry" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/ecr-repository"
  version = "~> 2.0"

  name_prefix = local.prefix

  # Every module-wide default is right here: IMMUTABLE tags, scan on push,
  # keep the last 10 images tagged "sha-", expire untagged after a day, AES256.
  repositories = {
    content  = {}
    resume   = {}
    identity = {}
    public   = {}
  }
}
