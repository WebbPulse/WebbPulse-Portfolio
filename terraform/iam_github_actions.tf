# ---------------------------------------------------------------------------
# The role GitHub Actions assumes to deploy, from the shared
# github-actions-role module: the account's GitHub OIDC provider, the role and
# its single inline deploy policy.
#
# The statement order below is the order the hand-written policy had, and the
# module renders a one-entry Action or Resource as a bare JSON string the same
# way the hand-written jsonencode() did, so the stored documents do not change.
# ---------------------------------------------------------------------------

# The key the access gate's origin-verify SecureString parameter is encrypted
# with. This is the only remaining SSM read in the application.
data "aws_kms_alias" "ssm" {
  name = "alias/aws/ssm"
}

locals {
  # Behind the staging access gate the backend smoke test calls the API host
  # directly and needs the origin-verify header value from SSM.
  github_actions_gate_statements = [for statement in [
    {
      actions   = ["ssm:GetParameter"]
      resources = [one(module.staging_access_gate[*].origin_verify_ssm_parameter_arn)]
    },
    {
      actions   = ["kms:Decrypt"]
      resources = [data.aws_kms_alias.ssm.target_key_arn]
      condition = {
        StringEquals = { "kms:ViaService" = ["ssm.${var.aws_region}.amazonaws.com"] }
      }
    },
  ] : statement if local.staging_gate_enabled]
}

locals {
  # The shared registry lives in the Artifacts account, in this region. Written out rather than
  # read from the Artifacts workspace's remote state on purpose: a remote state data source would
  # make every plan here depend on that workspace being readable and on its last apply having
  # succeeded, to learn a handful of ARNs that a fixed account id and a fixed name already
  # determine. The statement shapes below are copied from the Artifacts root's own
  # codeartifact_consumer_policy_statements and consumer_policy_json outputs, which are the
  # authoritative description of what a consumer attaches on its side.
  artifacts_account_id = "432410731887"

  codeartifact_domain_arn = "arn:aws:codeartifact:${var.aws_region}:${local.artifacts_account_id}:domain/webbpulse"

  # ReadFromRepository is all-or-nothing per repository, so the read grant names every repository in
  # the domain rather than trying to narrow to the one holding the webbpulse package. shared is the
  # fan-in CI actually points pip at; the four behind it are what shared resolves through.
  codeartifact_repository_arns = [
    for name in ["npm", "npm-store", "pypi-store", "python", "shared"] :
    "arn:aws:codeartifact:${var.aws_region}:${local.artifacts_account_id}:repository/webbpulse/${name}"
  ]

  # The base layer every domain image is built FROM, pulled cross account at build time.
  shared_base_image_repository_arn = "arn:aws:ecr:${var.aws_region}:${local.artifacts_account_id}:repository/webbpulse/python-lambda-base"

  # The four domain function ARNs, composed from their names rather than read
  # out of module.lambda_domain[*].function_arn. Referencing the module outputs
  # made this role depend on the functions themselves, and that ordering cannot
  # be satisfied on a fresh environment: the functions are container image
  # functions, so they cannot be created until an image has been pushed to ECR,
  # and nothing can push one until this role exists to carry the EcrAuth and
  # EcrPushDomainImages statements. A targeted apply of the role pulled the
  # function creation in with it and deadlocked the promotion. Composing the
  # ARNs breaks the cycle, and it is valid IAM either way: a policy may name the
  # ARN of a resource that does not exist yet, it simply grants nothing until it
  # does. The name here is the same expression lambda_domains.tf passes as
  # function_name, and the module uses it verbatim, so the two cannot drift
  # without this file changing too.
  lambda_domain_function_arns = [
    for name in sort(keys(local.lambda_domains)) :
    "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${local.prefix}-${name}"
  ]

  # Reading the shared webbpulse package during the container build. Three separate statements
  # because the three actions take three different resources: GetAuthorizationToken is domain
  # level, the read actions are per repository, and sts:GetServiceBearerToken has no resource of
  # its own at all. The last is the one most often missed: it lives in the caller's own identity
  # policy, and without it get-authorization-token fails with a denial that names no CodeArtifact
  # action. Its condition pins it to CodeArtifact so the grant cannot mint a bearer token for
  # another service.
  github_actions_codeartifact_statements = [
    {
      sid       = "CodeArtifactToken"
      actions   = ["codeartifact:GetAuthorizationToken"]
      resources = [local.codeartifact_domain_arn]
    },
    {
      sid = "CodeArtifactRead"
      actions = [
        "codeartifact:DescribePackageVersion",
        "codeartifact:DescribeRepository",
        "codeartifact:GetPackageVersionAsset",
        "codeartifact:GetPackageVersionReadme",
        "codeartifact:GetRepositoryEndpoint",
        "codeartifact:ListPackageVersionAssets",
        "codeartifact:ListPackageVersionDependencies",
        "codeartifact:ListPackageVersions",
        "codeartifact:ListPackages",
        "codeartifact:ReadFromRepository",
      ]
      resources = local.codeartifact_repository_arns
    },
    {
      sid       = "CodeArtifactBearerToken"
      actions   = ["sts:GetServiceBearerToken"]
      resources = ["*"]
      condition = {
        StringEquals = {
          "sts:AWSServiceName" = ["codeartifact.amazonaws.com"]
        }
      }
    },
  ]
}

module "github_actions_role" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/github-actions-role"
  version = "~> 1.1"

  role_name = "${local.prefix}-github-actions-deploy"

  # Scoped to the two GitHub Environments the deploy jobs bind to, not to the
  # repository as a whole. Both deploy-backend.yml and deploy-frontend.yml set
  # environment: production on main and staging otherwise, so those are the only
  # subjects GitHub ever mints for a job that reaches AWS_DEPLOY_ROLE_ARN. Their
  # workflow_dispatch trigger runs the same environment-bound job, so it is
  # covered too. The previous ":*" also admitted a pull request branch, which is
  # what the read-only CI role below exists to stop needing.
  subjects = [
    "repo:WebbPulse@185014056/WebbPulse-Portfolio@1029410045:environment:staging",
    "repo:WebbPulse@185014056/WebbPulse-Portfolio@1029410045:environment:production",
  ]

  policy_statements = concat([
    # Lambda: point a function at freshly published code. The four domain
    # functions take an image tag the container build has already pushed to
    # ECR. The monolith's zip deploy was the other consumer of this statement
    # and is gone with the function, so this now names four ARNs rather than
    # five.
    {
      actions = [
        "lambda:UpdateFunctionCode",
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration",
        "lambda:PublishVersion",
      ]
      resources = local.lambda_domain_function_arns
    },
    # Lambda: invoke the four domain functions directly for the post deploy
    # smoke probes. An Invoke with a synthetic HTTP API event proves a freshly
    # shipped image answers without depending on the gateway, the gate or DNS,
    # which is why it stayed after the routes were cut over.
    {
      actions   = ["lambda:InvokeFunction"]
      resources = local.lambda_domain_function_arns
    },
    # S3: read the artifacts bucket. Nothing writes to it since the monolith's
    # zip deploy was retired, and the grant is kept read-only so a rollback can
    # still fetch the last zip the monolith was deployed from without leaving a
    # write grant on a bucket no pipeline writes.
    {
      actions   = ["s3:GetObject", "s3:ListBucket"]
      resources = [module.lambda_artifacts.bucket_arn, "${module.lambda_artifacts.bucket_arn}/*"]
    },
    # S3: sync frontend build artifacts
    {
      actions = [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket",
      ]
      resources = [
        module.frontend.bucket_arn,
        "${module.frontend.bucket_arn}/*",
      ]
    },
    # CloudFront: invalidate the cache after a frontend deploy
    {
      actions = [
        "cloudfront:CreateInvalidation",
        "cloudfront:GetInvalidation",
      ]
      resources = [module.frontend.distribution_arn]
    },
    # ECR: authenticate to this account's registry. GetAuthorizationToken is a
    # registry level action that takes no resource of its own, which is why it
    # is a statement on "*" rather than folded into the push grant below.
    {
      sid       = "EcrAuth"
      actions   = ["ecr:GetAuthorizationToken"]
      resources = ["*"]
    },
    # ECR: push a domain image, and read back the manifest the build workflow
    # asserts on. Get and SetRepositoryPolicy are here so that creating a
    # container image function can write Lambda's own
    # LambdaECRImageRetrievalPolicy statement onto the repository, which is
    # what keeps the image pullable when Lambda re-fetches it later.
    {
      sid = "EcrPushDomainImages"
      actions = [
        "ecr:BatchCheckLayerAvailability",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:GetRepositoryPolicy",
        "ecr:SetRepositoryPolicy",
      ]
      resources = module.registry.repository_arns_list
    },
    # ECR: pull the shared base image the domain Dockerfiles build FROM. It
    # lives in the Artifacts account, which grants the other half on the
    # repository itself.
    {
      sid = "SharedBaseImagePull"
      actions = [
        "ecr:BatchGetImage",
        "ecr:DescribeImages",
        "ecr:GetDownloadUrlForLayer",
      ]
      resources = [local.shared_base_image_repository_arn]
    },
  ], local.github_actions_codeartifact_statements, local.github_actions_gate_statements)
}

# ---------------------------------------------------------------------------
# The role pull request CI assumes, separate from the deploy role above.
#
# test-backend.yml calls the org reusable python-ci workflow, which needs an AWS
# identity for one thing only: minting a read-only CodeArtifact token so pip can
# install the `webbpulse` package. It was doing that with the deploy role, which
# can update Lambda code and push ECR images, and whose trust admitted every
# subject in the repository including a pull request branch. That means any pull
# request, from anyone who can open one, could assume a role that deploys.
#
# This role carries the CodeArtifact statements and nothing else, and its trust
# names the pull request subject plus the two branch refs, so the reusable
# workflow keeps working on pushes as well as pull requests.
# ---------------------------------------------------------------------------
module "github_actions_ci_role" {
  source  = "app.terraform.io/WebbPulse/platform-modules/aws//modules/github-actions-role"
  version = "~> 1.1"

  role_name        = "${local.prefix}-github-actions-ci"
  role_description = "Read-only CodeArtifact access for pull request CI in WebbPulse/WebbPulse-Portfolio. Deploy permissions live on the separate github-actions-deploy role."

  # The deploy role's module call owns this account's single
  # token.actions.githubusercontent.com provider; an account holds at most one
  # per URL, so this call trusts that one rather than creating a second.
  create_oidc_provider = false
  oidc_provider_arn    = module.github_actions_role.oidc_provider_arn

  subjects = [
    "repo:WebbPulse@185014056/WebbPulse-Portfolio@1029410045:pull_request",
    "repo:WebbPulse@185014056/WebbPulse-Portfolio@1029410045:ref:refs/heads/staging",
    "repo:WebbPulse@185014056/WebbPulse-Portfolio@1029410045:ref:refs/heads/main",
  ]

  inline_policy_name = "codeartifact-read"

  policy_statements = local.github_actions_codeartifact_statements
}
