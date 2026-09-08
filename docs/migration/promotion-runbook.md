# Promoting the per-domain split from staging to production

This is the operator runbook for the release PR that takes `staging` into `main`
and moves production from the single zip-based monolith to the four per-domain
container-image Lambdas. It is written for someone with HCP Terraform API access
and GitHub access who confirms every apply by hand.

Read `docs/migration/cutover-log.md` first. That file records what actually
happened on staging, cut by cut, and this file is the production translation of
it. Where the two disagree, the cutover log is the record of fact and this file
is the plan.

Everything below that could be verified from the repository, the GitHub API or
the HCP Terraform API on 2026-09-08 has been. Anything that could not is marked
**verify by hand** and says why.

## Contents

1. [What production is missing](#1-what-production-is-missing)
2. [Pre-flight](#2-pre-flight)
3. [Apply sequencing](#3-apply-sequencing)
4. [The HCP Terraform API calls](#4-the-hcp-terraform-api-calls)
5. [Step by step](#5-step-by-step)
6. [Verification and rollback](#6-verification-and-rollback)
7. [Work outside Terraform](#7-work-outside-terraform)
8. [What is not included](#8-what-is-not-included)

## 1. What production is missing

Production runs `main` at `45a177d3f72bc6c513e69459bbaa86395bb0f309`. Staging is
25 commits ahead:

```
git log origin/main..origin/staging --oneline
```

The last production apply was `run-CJs3x3rmnKA67zH8` on 2026-09-07 at 09:33 UTC,
from the merge of PR #91. Nothing from the per-domain split has reached it.

Production today:

- one zip-based function `webbpulse-production-api`, Python 3.13, arm64, 512 MB,
  15 second timeout, handler `app.lambda_handler.handler`
  (`terraform/lambda.tf` on `origin/main`)
- two route keys on the HTTP API, `ANY /{proxy+}` and `ANY /`, both pointing at
  the `legacy` integration. `default_integration` is already `null`, so
  production has **no `$default` route today either**
  (`terraform/apigateway.tf:31-37` on `origin/main`)
- nine DynamoDB tables. `rate-limits` does not exist
- alarms from `api-alarms ~> 1.7` in the single-function shape:
  `webbpulse-production-lambda-errors`, `webbpulse-production-lambda-throttles`,
  and one metric filter keyed `api`
- no ECR repositories, no `github-actions-ci` role, no CodeArtifact or ECR
  grants on the deploy role
- X-Ray trace storage still on X-Ray rather than CloudWatch Logs, and the AWS
  provider still on the 5.x line

What the release brings, in one merge:

| Area | Change |
|---|---|
| `terraform/ecr.tf` | new file, four repositories `webbpulse-production/{content,resume,identity,public}` from `ecr-repository ~> 2.0` |
| `terraform/lambda_domains.tf` | new file, four image functions from `lambda-function ~> 2.1`, four roles, four runtime policies, four log groups, plus the `bootstrap_image_tag` variable |
| `terraform/lambda.tf` | the monolith function, its role, its runtime policy and its log group are deleted. The artifacts bucket and the placeholder stay |
| `terraform/apigateway.tf` | 21 explicit route keys across four integrations replace the two monolith keys. `default_integration` stays `null` |
| `terraform/dynamodb.tf` | adds the `rate-limits` table |
| `terraform/monitoring.tf` | `api-alarms` moves `~> 1.7` to `~> 2.1` and from the one-function form to the aggregate form |
| `terraform/iam_github_actions.tf` | ECR push, cross-account ECR pull, CodeArtifact read and Lambda invoke on the deploy role; a new read-only `github-actions-ci` role |
| `.github/workflows/deploy-backend.yml` | the monolith `deploy` job is gone. The `resolve-env`, `build-images`, `image-map`, `deploy-images`, `smoke-domains`, `verify-route-cuts` chain replaces it |
| `terraform/transaction_search.tf` | new file, switches X-Ray trace storage to CloudWatch Logs account-wide and adopts the `Default` indexing rule at 1 percent |
| `terraform/versions.tf` | the AWS provider moves from `~> 5.0` to `~> 6.46` |

### The ordering problem, stated exactly

`terraform/lambda_domains.tf:163-165` creates each function from
`"${module.registry.repository_urls[each.key]}:${var.bootstrap_image_tag}"`, and
`terraform/ecr.tf:17-31` creates those repositories in the same configuration.
Lambda pulls and optimises the image at `CreateFunction`, so a tag that does not
resolve fails the create. The variable's own description says so
(`terraform/lambda_domains.tf:127`):

> Lambda pulls and optimises the image when it creates the function, so a tag
> that does not resolve fails the create: the tag named here must already exist
> in all four repositories before the first apply.

On staging this never arose, because the work was staged across PRs: ECR
repositories applied in `run-feu6etx8WT5nHh9A` (2026-09-07 21:07), CI pushed
images, `bootstrap_image_tag` was set on the workspace, and only then did
`run-Y3k62yTzp53rGBDQ` (2026-09-07 23:03) create the functions. A single
staging-to-main merge plans all of it at once and the four Lambda creates fail.

There is a second, independent instance of the same problem. The functions must
exist before `deploy-images` can point them at an image, and
`deploy-images` fails hard rather than skipping when they do not. Section 3
resolves both.

## 2. Pre-flight

Everything in this section must be true before the release PR is merged. The
"State" column records what was observed on 2026-09-08.

### 2.1 HCP Terraform workspace `WebbPulse-Portfolio` (ws-JpNLUhFzVCzMDgAN)

Settings confirmed through the API:

| Setting | Value |
|---|---|
| `auto-apply` | `false`. Every apply is confirmed by hand |
| `terraform-version` | `1.14.8` |
| `working-directory` | `terraform` |
| `vcs-repo.branch` | `main` |
| `trigger-patterns` | `/terraform/**/*` |
| `speculative-enabled` | `true` |

The trigger pattern matters for sequencing: the release PR touches
`terraform/**`, so merging it **will** queue a VCS run automatically. That run
is the one to discard in option (a).

Workspace variables today:

| Key | Category | State |
|---|---|---|
| `route53_zone_id` | terraform | `Z01273391K7FAD6GLXNTW`, set |
| `route53_write_role_arn` | terraform | `arn:aws:iam::488386929690:role/WebbPulse-Portfolio-Route53`, set |
| `admin_username` | terraform, sensitive | set |
| `admin_password` | terraform, sensitive | set |
| `admin_email` | terraform, sensitive | set |
| `TFC_AWS_PROVIDER_AUTH` | env | `true` |
| `TFC_AWS_RUN_ROLE_ARN` | env | `arn:aws:iam::036807648992:role/WebbPulse-Terraform` |
| `TFC_AWS_WORKLOAD_IDENTITY_AUDIENCE` | env | `aws.workload.identity` |
| **`bootstrap_image_tag`** | terraform | **absent. This is the blocking gap** |

`bootstrap_image_tag` has no default (`terraform/lambda_domains.tf:126-134`), so
the plan fails outright until it is set. That is a better failure than a plan
that succeeds and an apply that does not, and it is what step 5.4 sets.

Two variables staging has that production deliberately does not, and must not
be given:

- `environment` is unset on production, and `terraform/variables.tf:7-16`
  defaults it to `"production"`. Leave it unset.
- `staging_profile` is unset on production, and `terraform/variables.tf:18-32`
  defaults it to `"full"`. Leave it unset. `staging_access_gate` and
  `staging_access_users` are likewise absent and default to `false` and `[]`
  (`terraform/variables.tf:56-66`), which is what makes
  `local.staging_gate_enabled` false in production
  (`terraform/locals.tf:31`) and the whole gate a no-op.

The consequence for verification: production has no access gate, the API is
reachable without the `x-origin-verify` header, and
`scripts/verify_route_cut.sh` sends no gate header on `production`
(`scripts/verify_route_cut.sh:301-302`, and `deploy-backend.yml:594` sets
`ORIGIN_VERIFY_PARAMETER` to the empty string on `main`).

### 2.2 GitHub repository-scoped variables

These are repository-scoped, so they **already apply to `main`**. They were set
for the staging rollout and no production-specific action is needed except to
understand what they now do.

| Variable | Value | Effect on `main` |
|---|---|---|
| `BACKEND_IMAGE_BUILD_ENABLED` | `true` | `resolve-env` runs on `main` pushes, so `build-images` runs |
| `BACKEND_IMAGE_DEPLOY_ENABLED` | `true` | `deploy-images` runs on `main` pushes |
| `CODEARTIFACT_DOMAIN_OWNER` | `432410731887` | correct for both, the Artifacts account is shared |
| `STAGING_DEPLOY_ENABLED` | `true` | no effect on `main`; the `if` is `github.ref_name == 'main' \|\| vars.STAGING_DEPLOY_ENABLED == 'true'` (`deploy-backend.yml:74-75`) |
| `CI_AWS_ROLE_ARN` | `arn:aws:iam::621554169154:role/webbpulse-staging-github-actions-ci` | **staging account.** See below |

`CI_AWS_ROLE_ARN` points at the staging account and is repository-scoped, so it
is the same value on every branch. That is deliberate and documented at
`terraform/outputs.tf:80-83`:

> Set it as the `CI_AWS_ROLE_ARN` repository variable (staging value only, since
> pull request checks run against staging).

It is only used by pull request CI to mint a read-only CodeArtifact token, and
the staging CI role's trust already names `ref:refs/heads/main`
(`terraform/iam_github_actions.tf:243`), so a push to `main` can assume it. No
change is needed. Do **not** repoint it at production: production's own CI role
is created by this release and has no purpose yet.

The two repository-scoped gates are the sharpest edge in this whole promotion.
Because `BACKEND_IMAGE_BUILD_ENABLED` and `BACKEND_IMAGE_DEPLOY_ENABLED` are
already `true`, the moment the release PR merges, a push to `main` that touches
`backend/**` will attempt the whole image chain against production. Section 3
turns that from a hazard into the mechanism.

### 2.3 GitHub `production` Environment

Deployment branch policy is `main` only, confirmed through the API. Contents as
observed:

| Name | Kind | Value | Status for this release |
|---|---|---|---|
| `AWS_DEPLOY_ROLE_ARN` | variable | `arn:aws:iam::036807648992:role/webbpulse-production-github-actions-deploy` | existed for the zip deploy, still correct. Read by `resolve-env` (`deploy-backend.yml:72-75`), `verify-route-cuts` (`:602`) and `deploy-frontend.yml:53` |
| `API_BASE_URL` | variable | `https://api.webbpulse.com` | existed. Read by `deploy-frontend.yml:47` |
| `FRONTEND_S3_BUCKET` | variable | `webbpulse-production-frontend` | existed. `deploy-frontend.yml:94` |
| `CLOUDFRONT_DISTRIBUTION_ID` | variable | `EZ8SO4AO1VN9` | existed. `deploy-frontend.yml:101` |
| `LAMBDA_ARTIFACT_BUCKET` | variable | `webbpulse-production-lambda-artifacts` | existed for the zip deploy. **Now unreferenced** by any workflow on `staging` |
| `LAMBDA_FUNCTION_NAME` | variable | `webbpulse-production-api` | existed for the zip deploy. **Now unreferenced**. Its Terraform output is gone (`terraform/outputs.tf:56-58`) |
| `ECR_REPOSITORY_NAME` | variable | `webbpulse-production-backend` | stale. Referenced by no workflow on either branch |
| `APP_RUNNER_SERVICE_ARN` | variable | `arn:aws:apprunner:us-west-2:036807648992:service/webbpulse-production-backend/...` | stale, from a pre-Lambda architecture. Referenced by no workflow |
| `TFC_API_TOKEN` | secret | set | existed. Only used by `deploy-frontend.yml:59`; `deploy-backend.yml` no longer polls HCP |

**No new Environment variable or secret is required by this release.** Every
`vars.*` and `secrets.*` reference in the two deploy workflows on `staging`
resolves against what `production` already holds. The complete reference list:

- `deploy-backend.yml`: `vars.STAGING_DEPLOY_ENABLED`,
  `vars.BACKEND_IMAGE_BUILD_ENABLED`, `vars.AWS_DEPLOY_ROLE_ARN`,
  `vars.CODEARTIFACT_DOMAIN_OWNER`, `vars.BACKEND_IMAGE_DEPLOY_ENABLED`
- `deploy-frontend.yml`: `vars.STAGING_DEPLOY_ENABLED`, `vars.API_BASE_URL`,
  `vars.AWS_DEPLOY_ROLE_ARN`, `vars.FRONTEND_S3_BUCKET`,
  `vars.CLOUDFRONT_DISTRIBUTION_ID`, `secrets.TFC_API_TOKEN`

Four variables become dead on `production` after this release:
`LAMBDA_FUNCTION_NAME`, `LAMBDA_ARTIFACT_BUCKET`, `ECR_REPOSITORY_NAME` and
`APP_RUNNER_SERVICE_ARN`. Leave all four in place through the release. They cost
nothing, and `LAMBDA_FUNCTION_NAME` plus `LAMBDA_ARTIFACT_BUCKET` are the two
values a manual rollback needs. Delete them in a later tidy-up PR once the
rollback window has closed, and only with the owner's agreement (section 7).

One asymmetry worth noting rather than fixing: the `staging` Environment has no
`TFC_API_TOKEN`, so `deploy-frontend.yml`'s HCP wait step is skipped on staging
and runs on production (`deploy-frontend.yml:28`,
`TFC_WAIT_ENABLED: ${{ secrets.TFC_API_TOKEN != '' }}`). That is a real
behavioural difference between the two branches, and on production it is the
behaviour you want: a frontend sync will wait out an in-flight Terraform apply.

### 2.4 OIDC trust subjects

`terraform/iam_github_actions.tf:113-116` gives the deploy role exactly two
subjects:

```
"repo:WebbPulse@185014056/WebbPulse-Portfolio@1029410045:environment:staging",
"repo:WebbPulse@185014056/WebbPulse-Portfolio@1029410045:environment:production",
```

These are the immutable-id subject forms, and `environment:production` is
already present. The role in the production account is
`webbpulse-production-github-actions-deploy` and its trust policy is rewritten
by this release, but the subject list does not change from what production
already has, because both branches carry the same two lines. **Verify by hand**
that the production role's current trust policy already names
`environment:production` in the immutable form: this file is what Terraform will
converge it to, so a mismatch shows up as a role trust update in the plan rather
than a failure, but a mismatch that is not in the plan means something was
edited outside Terraform.

The new CI role's subjects (`terraform/iam_github_actions.tf:240-244`) include
`pull_request` and both branch refs. In the production account this role is
created but nothing uses it, because `CI_AWS_ROLE_ARN` stays pointed at staging.

### 2.5 CodeArtifact read for CI

`terraform/iam_github_actions.tf:65-97` defines three statements the container
build needs, and all three go onto the production deploy role by this release:

- `codeartifact:GetAuthorizationToken` on
  `arn:aws:codeartifact:us-west-2:432410731887:domain/webbpulse`
- ten read actions on the five repositories `npm`, `npm-store`, `pypi-store`,
  `python`, `shared`
- `sts:GetServiceBearerToken` on `*`, conditioned on
  `sts:AWSServiceName = codeartifact.amazonaws.com`

The third is the one that is most often missed, and
`docs/migration/container-image-workflow-gaps.md:53-56` records why: without it,
`get-authorization-token` fails with a denial that names no CodeArtifact action
at all. It is in the configuration, so the apply grants it. There is nothing to
do by hand, but if step 5.5's build fails with an opaque denial, this is the
first thing to check.

The cross-account half is in the Artifacts account (432410731887) and is not
managed by this repository. Staging's builds already prove the domain and
repository policies admit a Portfolio deploy role. **Verify by hand** that they
admit the production role too, or expect the first `build-images` run on `main`
to fail at the CodeArtifact login. The same applies to the shared base image:
`terraform/iam_github_actions.tf:56` names
`arn:aws:ecr:us-west-2:432410731887:repository/webbpulse/python-lambda-base`,
and the repository policy on the Artifacts side has to grant the pull.
`container-image-workflow-gaps.md:70-78` records that this failure presents as a
Docker 401 rather than as an IAM denial, which is worth knowing before you spend
time on the wrong side of it.

### 2.6 Lambda concurrency quota

Project memory records that a raise of the account concurrent-executions limit
to 1000 was requested in all four accounts on 2026-09-07, after a limit of 10
caused `lambda-throttles` and `api-5xx` alarms. **The outcome is not recorded in
this repository and could not be checked from here: this runbook was written
without AWS credentials.**

This matters more for production than it did for staging. The split replaces one
function with four, and a cold start on each is four concurrent executions where
there was one. At a limit of 10 the four functions plus any real traffic will
throttle, and `webbpulse-production-lambda-throttles-aggregate` alarms at
`GreaterThanThreshold 0` (`terraform/monitoring.tf:54`), so it will fire on the
first throttle.

**Verify by hand before step 5.6:**

```
aws service-quotas get-service-quota \
  --service-code lambda \
  --quota-code L-B99A9384 \
  --region us-west-2
```

against account 036807648992. If the value is still 10, stop and raise it with
the owner before cutting routes. Requesting a quota increase is a support
interaction and needs the owner's explicit approval first (section 7).

### 2.7 Capture the rollback artifact before you start

The last zip deployed to production is at
`s3://webbpulse-production-lambda-artifacts/backend/87138c18aee085b2d0fc7140b65a411a1e052c86.zip`.

That sha is the head of `main` on the last successful `deploy-backend` run
against `main`, GitHub Actions run `34092381780` on 2026-09-07 at 06:47 UTC. The
key shape comes from `ARTIFACT_KEY: backend/${{ github.sha }}.zip`
(`.github/workflows/deploy-backend.yml:31` on `origin/main`).

Write it down now. After this release merges, the `deploy` job that wrote those
zips no longer exists, so no new one is ever produced, and the rollback target
only gets staler. `docs/migration/cutover-log.md:977-983` makes the same point
about staging.

The bucket survives the release on purpose (`terraform/lambda.tf:11-17`), and
the deploy role keeps read access to it (`terraform/iam_github_actions.tf:145`).

### 2.8 Transaction Search and the AWS provider bump

PR #119 merged into `staging` on 2026-09-08 at 02:00 UTC, after the monolith
retirement, so it is inside this promotion. It does two things that deserve a
decision before the apply rather than during it.

**The provider moves from `~> 5.0` to `~> 6.46`** (`terraform/versions.tf:7`).
That is a major version jump, and it is landing in the same apply that destroys
the function currently serving production. The one source change it forced is
visible at `terraform/outputs.tf:8`, where `data.aws_region.current.name` became
`data.aws_region.current.region`. Staging applied the bump without incident, and
production's configuration is the same configuration, so the expectation is that
it is clean. **Verify by hand** by reading the plan for changes to resources that
this release does not otherwise touch. A provider major version can rewrite
attribute defaults, and any update on a DynamoDB table, the CloudFront
distribution or the ACM certificate is provider drift rather than intended
change. If the plan contains such an update, stop and read it before confirming.

**Transaction Search is account-wide and effectively one-way.** The file says so
plainly (`terraform/transaction_search.tf:12-19`): the switch applies to
everything in account 036807648992 that writes X-Ray segments, not only the
Portfolio functions. Spans stop being stored as X-Ray traces and are written as
structured logs to the `aws/spans` log group, which moves them onto CloudWatch
Logs pricing. The indexing rule keeps 1 percent of traceIds indexed, which is
the AWS default and the free tier.

The part to understand before confirming is the destroy behaviour
(`terraform/transaction_search.tf:21-28`): neither
`aws_xray_trace_segment_destination` nor `aws_xray_indexing_rule` reverts
anything in AWS when it is removed from the configuration. Both adopt an account
singleton rather than creating a new object. Removing them from Terraform leaves
the destination on `CloudWatchLogs` and the `Default` rule at whatever
percentage was last applied. **Reverting is an explicit change of `destination`
back to `"XRay"` and another apply, not a `terraform destroy` and not a revert
of the merge.** Treat this as a deliberate account-level change to production
observability that happens to be riding along with the promotion, and confirm
with the owner that they want it in the same release (section 7).

If the owner would rather not take it in this release, it can be removed from
the promotion by reverting PR #119 on `staging` before opening the release PR.
Do not try to exclude it with `target-addrs` on the full apply: a targeted apply
that skips it would leave `main` and the workspace state disagreeing about a
file that is present in the configuration, and the next unrelated run would
apply it anyway without anyone reading this section.

The reason it is here at all is PR #117, which is still open. AWS requires
Transaction Search before the X-Ray OTLP endpoint will accept spans
(`terraform/transaction_search.tf:4-10`), so #119 is the prerequisite that #117
waits on. Applying #119 without #117 is harmless: it changes where spans are
stored for anything already writing them and nothing starts exporting OTLP until
#117 ships.

### 2.9 Pre-flight checklist

- [ ] `bootstrap_image_tag` is **not** yet set on ws-JpNLUhFzVCzMDgAN. It gets set at step 5.4, not before: it must name a tag that exists
- [ ] `environment`, `staging_profile`, `staging_access_gate`, `staging_access_users` are all absent from the production workspace and stay absent
- [ ] The production account's Lambda concurrent-executions quota is confirmed to be above 10 (section 2.6)
- [ ] The rollback zip key is recorded (section 2.7)
- [ ] The Artifacts account admits the production deploy role for CodeArtifact and for the base image pull (section 2.5)
- [ ] The owner has confirmed the SNS subscription plan (section 7)
- [ ] The owner has agreed to take the account-wide Transaction Search switch and the AWS provider major bump in this release, or PR #119 has been reverted on `staging` first (section 2.8)
- [ ] PR #117 is resolved one way or the other (section 8)

## 3. Apply sequencing

### What the workflow actually does when the functions do not exist

This decides the whole sequence, so it is worth quoting.

`build-images` needs only `resolve-env`, and `resolve-env` needs only
`vars.BACKEND_IMAGE_BUILD_ENABLED` and `vars.AWS_DEPLOY_ROLE_ARN`
(`deploy-backend.yml:72-75`). It touches ECR and CodeArtifact and nothing else.
**It does not care whether the Lambda functions exist.** It does require the ECR
repositories to exist, because it pushes to
`webbpulse-${{ needs.resolve-env.outputs.name }}/${{ matrix.domain }}`
(`deploy-backend.yml:160`).

`deploy-images` is the one that fails. Its guard is
(`deploy-backend.yml:344-348`):

```yaml
    if: >-
      needs.image-map.result == 'success'
      && vars.BACKEND_IMAGE_DEPLOY_ENABLED == 'true'
      && needs.image-map.outputs.function-image-map != ''
      && needs.image-map.outputs.function-image-map != '{}'
```

Every one of those is satisfied by a successful build. `image-map` derives the
function names arithmetically from the repository name
(`deploy-backend.yml:261-262`):

```python
              domain = manifest["repository"].rsplit("/", 1)[-1]
              out[f"webbpulse-{env}-{domain}"] = manifest["image_uri"]
```

so it emits `webbpulse-production-content` and the other three whether or not
those functions exist. `deploy-images` then hands that map to
`lambda-image-deploy.yml@v1`, which calls `UpdateFunctionCode` on names that do
not resolve. That fails with `ResourceNotFoundException`.

So on a push to `main` before the functions exist: **`build-images` succeeds and
pushes all four images; `deploy-images` fails.** That is exactly the shape the
sequencing needs, and it is why option (a) below works. The failure is loud,
recoverable and harmless: `smoke-domains` skips because it requires
`needs.deploy-images.result == 'success'` (`deploy-backend.yml:416`), and
`verify-route-cuts` skips too, because its guard is
`needs.deploy-images.result != 'failure'` (`deploy-backend.yml:575-578`).

Re-runs are safe. `container-image-workflow-gaps.md:140` records that
`container-image.yml@v1.2.0` added `skip-if-tag-exists`, defaulting to `true`:

> It resolves the tag with `aws ecr batch-get-image` (not `describe-images`, for
> the permission reason this document gave) and, when the tag is already there,
> skips the build and emits the existing digest as the outputs. [...] The
> default is the wanted behaviour, and a rerun of a green commit is now green.

That matters here because the repositories are created with `IMMUTABLE` tags
(`terraform/ecr.tf:23`). Without the guard, a re-run of the same commit would
push an existing tag and fail with `ImageTagAlreadyExistsException` whenever the
rebuild was not byte-identical. With it, a re-run skips the build and re-emits
the existing digest, so **you can re-run the `deploy-images` job alone** after
the functions exist and it will use the images the earlier run pushed. That is
step 5.6.

One consequence of `skip-if-tag-exists` to keep in mind: it keys on the tag
existing in the target repository, and production's repositories are separate
from staging's. The first production build of a given sha therefore always
builds fresh rather than copying staging's image. The base image is pinned by
digest (`container-image-workflow-gaps.md:66`), which is what makes that rebuild
honest, but the resulting production images are not guaranteed byte-identical to
the staging images you validated.

### The options

**(a) Merge, discard the VCS run, targeted ECR apply, let CI push, set the tag,
full apply.** Six steps, one PR, no throwaway commits on `main`.

**(b) Two-PR promotion, ECR repositories first.** A first PR to `main`
containing only `terraform/ecr.tf`, then the rest. Cleaner to describe, but it
puts a commit on `main` that exists on no branch and is not a merge of
`staging`, which breaks the invariant that `main` is always a fast-forward-ish
promotion of `staging`. It also means `main` and `staging` are briefly
divergent in a way the next release has to reconcile, and `CLAUDE.md`'s
branching rules are explicit that the release boundary is one PR from `staging`
into `main`. It needs two release PRs, two review cycles and two merges to
achieve what (a) does with one merge and one extra API call.

**(c) Set `bootstrap_image_tag` to a tag that already exists somewhere.** Does
not work. The tag must exist in *these four repositories*, in this account, and
they do not exist until the apply creates them.

**(d) Add a `depends_on` or a `terraform_data` gate.** Terraform cannot express
"wait for a CI job to push an image", and adding a provisioner or a
null-resource poll would put a network wait inside an apply. Not viable.

**(e) Dispatch `deploy-backend.yml` manually on `main` before merging.** The
workflow has `workflow_dispatch` (`deploy-backend.yml:39`), so this is possible,
but before the merge `main` has no `backend/Dockerfile` and no domain packages,
so the build has nothing to build. Not viable.

### Recommendation: option (a)

It is one release PR, which is what the branching model asks for. It uses the
repository-scoped image gates as the mechanism rather than fighting them: the
merge's own push to `main` is what pushes the images, so no extra dispatch is
needed and no throwaway commit is created. The one `deploy-images` failure it
produces is expected, is documented here, and is cleared by re-running that job
once. And the targeted first apply is genuinely safe: `module.registry` creates
four repositories and four lifecycle policies and touches nothing that serves
traffic.

Option (b) is the fallback if the targeted apply is refused for any reason, for
instance if the workspace's plan cannot be constrained the way step 5.2 assumes.
It reaches the same end state.

## 4. The HCP Terraform API calls

The token lives at `~/.terraform.d/credentials.tfrc.json`. Load it into the
shell once:

```bash
export TFC_TOKEN=$(python3 -c \
  "import json,os;print(json.load(open(os.path.expanduser('~/.terraform.d/credentials.tfrc.json')))['credentials']['app.terraform.io']['token'])")
export WS=ws-JpNLUhFzVCzMDgAN
export TFH="Authorization: Bearer $TFC_TOKEN"
export TFCT="Content-Type: application/vnd.api+json"
```

`ws-JpNLUhFzVCzMDgAN` is `WebbPulse-Portfolio`, the production workspace.
Staging is `ws-5SsqJj33we9fQJGY`. Getting these the wrong way round is the one
mistake this runbook cannot recover from, so every command below names `$WS`
rather than a literal.

**List recent runs.**

```bash
curl -sf -H "$TFH" \
  "https://app.terraform.io/api/v2/workspaces/$WS/runs?page%5Bsize%5D=5" \
| python3 -c "
import sys,json
for r in json.load(sys.stdin)['data']:
    a=r['attributes']
    print(r['id'], a['status'], a['created-at'][:19], repr((a.get('message') or '')[:60]))
"
```

**Discard a run.**

```bash
curl -sf -X POST -H "$TFH" -H "$TFCT" \
  -d '{"comment":"Discarded: the ECR repositories must exist before the domain functions can be created. See docs/migration/promotion-runbook.md step 5.2."}' \
  "https://app.terraform.io/api/v2/runs/<RUN_ID>/actions/discard"
```

**Create a targeted run.** `target-addrs` is a run attribute, not a variable.

```bash
curl -sf -X POST -H "$TFH" -H "$TFCT" \
  -d '{
    "data": {
      "type": "runs",
      "attributes": {
        "message": "Promotion step 1: create the four ECR repositories only",
        "target-addrs": ["module.registry"]
      },
      "relationships": {
        "workspace": { "data": { "type": "workspaces", "id": "'"$WS"'" } }
      }
    }
  }' \
  "https://app.terraform.io/api/v2/runs" \
| python3 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])"
```

Omitting `configuration-version` makes the run use the workspace's latest
configuration version, which after the merge is the merge commit. Confirm that
by reading the run back and checking its `message` names the merge.

**Read the plan counts.**

```bash
curl -sf -H "$TFH" "https://app.terraform.io/api/v2/runs/<RUN_ID>?include=plan" \
| python3 -c "
import sys,json
d=json.load(sys.stdin)
print('run status:', d['data']['attributes']['status'])
for i in d.get('included',[]):
    if i['type']=='plans':
        a=i['attributes']
        print('add', a.get('resource-additions'),
              'change', a.get('resource-changes'),
              'destroy', a.get('resource-destructions'))
"
```

**Read the plan resource by resource.** This is the check that matters more than
the counts, and it is how every plan shape in section 5 was derived from
staging's runs.

```bash
curl -sfL -H "$TFH" \
  "https://app.terraform.io/api/v2/runs/<RUN_ID>/plan/json-output" \
| python3 -c "
import sys,json
for rc in json.load(sys.stdin).get('resource_changes',[]):
    acts=rc['change']['actions']
    if acts!=['no-op']:
        print(','.join(acts).ljust(16), rc['address'])
"
```

The `-L` is required: the endpoint answers with a redirect to object storage.

**Confirm the apply.** Never run this without having read the resource list
above.

```bash
curl -sf -X POST -H "$TFH" -H "$TFCT" \
  -d '{"comment":"Confirmed against docs/migration/promotion-runbook.md step N. Plan matches the expected shape."}' \
  "https://app.terraform.io/api/v2/runs/<RUN_ID>/actions/apply"
```

**Set a workspace variable.**

```bash
curl -sf -X POST -H "$TFH" -H "$TFCT" \
  -d '{
    "data": {
      "type": "vars",
      "attributes": {
        "key": "bootstrap_image_tag",
        "value": "sha-<40 hex characters>",
        "category": "terraform",
        "sensitive": false,
        "description": "Seed image tag for the four per-domain functions. Only ever a seed: image_uri is on the module ignore_changes list."
      }
    }
  }' \
  "https://app.terraform.io/api/v2/workspaces/$WS/vars"
```

The value must match `^sha-[0-9a-f]{40}$` or the plan fails on the variable's
own validation (`terraform/lambda_domains.tf:130-133`).

## 5. Step by step

### 5.1 Open and merge the release PR

```bash
gh pr create --base main --head staging \
  --title "Promote: the per-domain split, the container image pipeline and the monolith retirement"
```

The PR body should link this runbook and say plainly that merging it does not
change AWS, because the production workspace is manual-apply. That is the real
gate (`CLAUDE.md`, "Protection").

Merge it. Two things happen immediately and automatically:

1. HCP queues a VCS-triggered run against `main`, because the merge touches
   `terraform/**` and the workspace's trigger pattern is `/terraform/**/*`.
2. GitHub queues `deploy-backend.yml` and `deploy-frontend.yml` on `main`,
   because the merge touches `backend/**` and `frontend/**`.

Do not confirm the HCP run.

### 5.2 Discard the VCS run and apply `module.registry` alone

Find the queued run with the runs-list call, confirm its `message` names the
merge, and discard it. Then create the targeted run from section 4 with
`"target-addrs": ["module.registry"]`.

**Expected plan: 8 to add, 0 to change, 0 to destroy.** Staging's equivalent was
`run-feu6etx8WT5nHh9A`, and its resource list was exactly:

```
create  module.registry.aws_ecr_lifecycle_policy.this["content"]
create  module.registry.aws_ecr_lifecycle_policy.this["identity"]
create  module.registry.aws_ecr_lifecycle_policy.this["public"]
create  module.registry.aws_ecr_lifecycle_policy.this["resume"]
create  module.registry.aws_ecr_repository.this["content"]
create  module.registry.aws_ecr_repository.this["identity"]
create  module.registry.aws_ecr_repository.this["public"]
create  module.registry.aws_ecr_repository.this["resume"]
```

Production's should be identical, with `webbpulse-production/` names instead of
`webbpulse-staging/`. If it is not, stop.

A targeted run prints a warning that the plan is not a complete representation
of the configuration. That is expected and is the point.

Confirm the apply. Nothing that serves traffic is touched: the monolith, its
routes and its integration are all outside `module.registry` and are not in this
plan at all.

### 5.3 Let the images build

The `deploy-backend.yml` run from the merge either is still queued or has
already failed at `build-images` because the repositories did not exist. Check:

```bash
gh run list --workflow=deploy-backend.yml --branch=main --limit=3
```

If it failed at `build-images`, re-run the failed jobs now that the repositories
exist:

```bash
gh run rerun <RUN_ID> --failed
```

If it has not started, or you want a clean run, dispatch one:

```bash
gh workflow run deploy-backend.yml --ref main
```

**Expected outcome: `build-images` succeeds for all four domains,
`image-map` succeeds, `deploy-images` fails, `smoke-domains` and
`verify-route-cuts` skip.** The `deploy-images` failure is the
`ResourceNotFoundException` from section 3 and is expected at this point.

Read the run summary. `image-map` writes the map to `$GITHUB_STEP_SUMMARY`
(`deploy-backend.yml:280-289`) including the line `Tag: sha-<sha>`. Record that
sha: it is what step 5.4 needs. It is the merge commit on `main`, since
`GITHUB_SHA` on a push to `main` is the merge commit.

Confirm all four images landed:

```bash
for d in content resume identity public; do
  aws ecr batch-get-image \
    --repository-name "webbpulse-production/$d" \
    --image-ids imageTag="sha-<sha>" \
    --region us-west-2 --query 'images[0].imageId' --output json
done
```

All four must resolve. `terraform/lambda_domains.tf:127` is explicit that a tag
that does not resolve fails the function create, and this is the last cheap
moment to catch a missing one.

### 5.4 Set `bootstrap_image_tag`

Use the variable-create call from section 4 with the sha from step 5.3.

This is a one-time act. The variable is only a seed:
`terraform/lambda_domains.tf:127` records that `image_uri` is on the module's
`ignore_changes` list, so the deploy step's `UpdateFunctionCode` is not undone
by the next plan and this value never needs changing again.

### 5.5 The full apply

Queue an untargeted run. Either push a no-op to `main`, or better, create one
through the API by omitting `target-addrs`:

```bash
curl -sf -X POST -H "$TFH" -H "$TFCT" \
  -d '{
    "data": {
      "type": "runs",
      "attributes": {
        "message": "Promotion step 2: the full per-domain split and the monolith retirement"
      },
      "relationships": {
        "workspace": { "data": { "type": "workspaces", "id": "'"$WS"'" } }
      }
    }
  }' \
  "https://app.terraform.io/api/v2/runs"
```

**Expected plan shape: about 64 to add, 6 to change, 12 to destroy.**

That figure is the union of every staging plan from `run-feu6etx8WT5nHh9A`
through `run-hGDixAENbR5eR62a`, less the 8 ECR resources already applied at step
5.2, and less the resources that were created and then destroyed inside
staging's sequence and therefore never appear in a one-shot plan. Staging's
sequence created `$default`, the `legacy` integration and the `legacy`
permission and then destroyed them; production never creates them, because it
already has `default_integration = null` and merges straight to the end state.

Read the full resource list with the `json-output` call and check it against
this. Grouped by what it is:

**Created, the four domain functions and their supporting resources (21):**

```
module.lambda_domain["content"].aws_lambda_function.this
module.lambda_domain["content"].aws_iam_role.this
module.lambda_domain["content"].aws_iam_role_policy.xray_write[0]
module.lambda_domain["content"].aws_cloudwatch_log_group.this
   ... and the same four for identity, public and resume
aws_iam_role_policy.lambda_domain["content"]
aws_iam_role_policy.lambda_domain["identity"]
aws_iam_role_policy.lambda_domain["public"]
aws_iam_role_policy.lambda_domain["resume"]
module.dynamodb.aws_dynamodb_table.this["rate-limits"]
```

**Created, the gateway surface (29):** four
`module.api.aws_apigatewayv2_integration.this["<domain>"]`, four
`module.api.aws_lambda_permission.this["<domain>"]`, and 21
`module.api.aws_apigatewayv2_route.this[...]` keys:

```
GET /                                  GET /health
GET /robots.txt                        GET /sitemap.xml
ANY /api/v1/projects                   ANY /api/v1/projects/{proxy+}
ANY /api/v1/experience                 ANY /api/v1/experience/{proxy+}
ANY /api/v1/skills                     ANY /api/v1/skills/{proxy+}
ANY /api/v1/education                  ANY /api/v1/education/{proxy+}
ANY /api/v1/certifications             ANY /api/v1/certifications/{proxy+}
ANY /api/v1/posts                      ANY /api/v1/posts/{proxy+}
ANY /api/v1/site-content               ANY /api/v1/site-content/{proxy+}
ANY /api/v1/admin                      ANY /api/v1/admin/{proxy+}
```

Twenty of those are pairs, plus `GET /health` and the three other `public`
literals. No key ends in a slash. If the plan contains a key ending in `/`,
**stop**: that is the failure staging hit on `run-wejfhcFYu9riFnvc`, where API
Gateway rejected every `ANY /api/v1/<collection>/` key with
`BadRequestException: Part of the given route key path is empty`. A green plan
is not evidence that a route key is valid
(`docs/migration/cutover-log.md:441-442`). The keys on `staging` today are
already corrected, so this should not recur; the check is cheap.

**Created, Transaction Search (4):**

```
aws_cloudwatch_log_group.spans
aws_cloudwatch_log_resource_policy.transaction_search_spans
aws_xray_trace_segment_destination.main
aws_xray_indexing_rule.default
```

These arrived on `staging` in PR #119 after the monolith retirement, so they are
part of this promotion and not a later release. Read section 2.8 before
confirming the apply: the trace destination switch is account-wide and is not
undone by removing the resource.

**Created, the CI role and the alarm filters (6):**

```
module.github_actions_ci_role.aws_iam_role.this
module.github_actions_ci_role.aws_iam_role_policy.this[0]
module.alarms.aws_cloudwatch_log_metric_filter.errors["content"]
module.alarms.aws_cloudwatch_log_metric_filter.errors["identity"]
module.alarms.aws_cloudwatch_log_metric_filter.errors["public"]
module.alarms.aws_cloudwatch_log_metric_filter.errors["resume"]
```

**Changed (6):**

```
module.alarms.aws_cloudwatch_metric_alarm.errors[0]
module.alarms.aws_cloudwatch_metric_alarm.lambda_aggregate_errors[0]      (created here, see note)
module.alarms.aws_cloudwatch_metric_alarm.lambda_aggregate_throttles[0]   (created here, see note)
module.api.aws_cloudwatch_log_group.access
module.github_actions_role.aws_iam_role.this
module.github_actions_role.aws_iam_role_policy.this[0]
```

The two aggregate alarms are a **create** on production rather than an update,
because production has never had them: staging created them in
`run-sUwatTS7Mzez3ieX` and then updated them in the retirement run. On
production they appear once, as creates. Adjust the counts accordingly if the
plan reads 62/4/12 rather than 60/6/12; the resource list is the thing to trust,
not the arithmetic.

`module.api.aws_cloudwatch_log_group.access` is the access log retention going
from 30 days to 7 (`terraform/apigateway.tf:310`).

**Destroyed (12):**

```
module.lambda_api.aws_lambda_function.this
module.lambda_api.aws_iam_role.this
module.lambda_api.aws_cloudwatch_log_group.this
aws_iam_role_policy.lambda_api
module.api.aws_apigatewayv2_integration.this["legacy"]
module.api.aws_lambda_permission.this["legacy"]
module.api.aws_apigatewayv2_route.this["ANY /"]
module.api.aws_apigatewayv2_route.this["ANY /{proxy+}"]
module.alarms.aws_cloudwatch_log_metric_filter.errors["api"]
module.alarms.aws_cloudwatch_metric_alarm.lambda_errors[0]
module.alarms.aws_cloudwatch_metric_alarm.lambda_throttles[0]
```

That is 11. The twelfth is whichever of the two old per-function alarms or the
`api` metric filter your plan actually enumerates; **verify against the plan
output rather than against this count.** The staging retirement destroyed 8 and
the alarms change destroyed 2, and production's set differs because it never had
`$default` to destroy.

**This is the destructive step, and here is what it destroys.**
`module.lambda_api.aws_lambda_function.this` is `webbpulse-production-api`. Once
it is gone, the zip in the artifacts bucket cannot bring it back: a zip is code,
not a function, and `aws lambda update-function-code` needs a function to update.
Restoring it means re-adding `module.lambda_api` to `terraform/lambda.tf` and
applying, and only then deploying the zip. Section 6.4 spells that out.

**The `$default` question does not arise on production.**
`terraform/apigateway.tf:31-37` on `origin/main` shows production reaches the
monolith through `ANY /{proxy+}` and `ANY /`, and `default_integration` is
already `null`. So unlike staging, production never has a `$default` route to
lose. What it does have is a window inside the apply where the two monolith keys
have been destroyed and some of the 21 new keys have not yet been created.
During that window a request to a path whose new key has not landed gets API
Gateway's own 404 with no `X-WebbPulse-Domain` header. There is no fall-through
and no monolith to catch it.

That window is real but short. API Gateway route creates and deletes are
individual API calls inside one apply, typically seconds. Terraform's ordering
is not guaranteed to create before destroy across unrelated resources, so plan
for the worst case: **a brief 404 window on every API path**, on the order of
seconds to a low number of minutes. There is no way to avoid it in a one-shot
apply, and staging accepted the same exposure. If the owner wants it avoided,
that means running the four cuts as four separate targeted applies on production
the way staging did, which is a larger and slower operation than this runbook
describes.

There is a second, longer window after the apply: the four functions exist and
carry only the bootstrap image, and they have never been invoked, so the first
request to each is a cold start on a container image. That is slower than a zip
cold start, and `scripts/verify_route_cut.sh` retries five times with a five
second sleep for exactly this reason (`scripts/verify_route_cut.sh:308`,
`:366-379`).

Confirm the apply, then go straight to step 5.6. Do not stop to celebrate: the
functions are running the bootstrap image and have not been through a deploy.

### 5.6 Re-run `deploy-images`

The functions now exist. Re-run the failed jobs from the run in step 5.3:

```bash
gh run rerun <RUN_ID> --failed
```

`build-images` re-runs, finds the tags already present in all four repositories,
and skips the builds while re-emitting the existing digests, because
`skip-if-tag-exists` defaults to `true`
(`container-image-workflow-gaps.md:140`). `image-map` reassembles the same
digest-pinned map. `deploy-images` calls `UpdateFunctionCode` on four functions
that now resolve, and publishes a version per deploy
(`deploy-backend.yml:370-374`).

**Expected outcome: every job green,** including `smoke-domains` and
`verify-route-cuts`.

`smoke-domains` invokes each function directly with a synthesised API Gateway
HTTP API v2 payload for `GET /health` and asserts a 200
(`deploy-backend.yml:414-571`). A 200 from `public` additionally proves the
least-privilege claim: `public` holds no Secrets Manager access at all
(`terraform/lambda_domains.tf:190`) and its `/health` reads the site-content
singleton.

`verify-route-cuts` runs `scripts/verify_route_cut.sh production <domain>` for
all four domains (`deploy-backend.yml:621-632`). On `main` it sends no gate
header, because `ORIGIN_VERIFY_PARAMETER` is the empty string there
(`deploy-backend.yml:594`) and the SSM read step is skipped.

If `deploy-images` fails again, read the reusable workflow's log before
re-running: the failure modes worth separating are a
`ResourceNotFoundException` (the apply did not actually land), a
`ResourceConflictException` (an apply is still in flight; the reusable workflow
retries these with a backoff, so a hard failure means something else), and an
`AccessDeniedException` naming `lambda:UpdateFunctionCode` (the deploy role's
policy update in step 5.5 did not apply).

### 5.7 The frontend

`deploy-frontend.yml` was also queued by the merge. It builds with
`VITE_API_BASE_URL=https://api.webbpulse.com/api/v1`, waits out any in-flight
Terraform run using the `production` Environment's `TFC_API_TOKEN`, syncs to
`webbpulse-production-frontend` and invalidates `EZ8SO4AO1VN9`.

Nothing in this release changes the frontend contract: ids stay integers, list
endpoints keep `skip`/`limit`, and the API base URL is unchanged. Let it run. If
it ran before step 5.5 finished, re-run it after, so the CloudFront
invalidation lands on the far side of the cut.

## 6. Verification and rollback

### 6.1 After step 5.2 (ECR)

```bash
aws ecr describe-repositories --region us-west-2 \
  --query 'repositories[?starts_with(repositoryName, `webbpulse-production/`)].repositoryName'
```

Four names. Nothing else changed, so nothing else needs checking. The monolith
is still serving every path.

### 6.2 After step 5.3 (images)

The `batch-get-image` loop from step 5.3. Four resolvable tags.

### 6.3 After steps 5.5 and 5.6 (the cut)

`verify-route-cuts` already ran all four domains in CI. Run them by hand too,
because CI ran them once and the interesting failures are the intermittent ones:

```bash
bash scripts/verify_route_cut.sh production public
bash scripts/verify_route_cut.sh production resume
bash scripts/verify_route_cut.sh production content
bash scripts/verify_route_cut.sh production identity
```

The base URL resolves to `https://api.webbpulse.com` for `production`
(`scripts/verify_route_cut.sh:299-304`). Set no `WEBBPULSE_ORIGIN_VERIFY` and no
`WEBBPULSE_GATE_COOKIE`: production has no access gate, and the script's gate
check block only runs when the environment is `staging`
(`scripts/verify_route_cut.sh:449`).

Expected `X-WebbPulse-Domain` values, per domain:

| Domain | Paths | Expected header | Expected status |
|---|---|---|---|
| `public` | `/health`, `/`, `/sitemap.xml`, `/robots.txt` | `public` | 200 |
| `resume` | both slash forms of the five collections, ten paths | `resume` | 200 |
| `content` | both slash forms of `posts` and `site-content`, four paths | `content` | 200 |
| `identity` | `/api/v1/admin/login`, `/api/v1/admin/login/`, `/api/v1/admin`, `/api/v1/admin/` | `identity` | 404 or 405, and that is correct |

`identity` is the one to read carefully. It serves exactly one route,
`POST /api/v1/admin/login`, so a GET to it answers 405 and a GET to the prefix
root answers 404, both **from the identity function**, both carrying the header.
`EXPECTED_CODES` is set to `200 404 405` for that reason
(`scripts/verify_route_cut.sh:285`). A 404 **with** the header is the identity
function saying it has no such path; a 404 **without** the header is API Gateway
saying no route key matched. Those are opposite verdicts on the same status
code, and the script separates them at `scripts/verify_route_cut.sh:393-400`.

A `NO ROUTE` verdict on any path is an outage on that path, not a warning. There
is no `$default` and no monolith to catch it.

A `monolith` verdict should be impossible: the function is destroyed. If one
appears, something re-created it.

Cross-check the access log if any response looks wrong. The log group is
`/aws/apigateway/webbpulse-production-api` and the `routeKey` field says which
key matched (`terraform/apigateway.tf:319`).

One behaviour settled empirically on staging and worth confirming holds on
production: `docs/migration/cutover-log.md:310-314` records that the
trailing-slash paths are matched by the **bare** key, because the gateway
normalises the slash before route selection. Both slash forms are probed for
every collection and prefix, so the verify script covers it.

Also check the frontend end to end. `/api/v1/projects?featured_only=true` is the
one request whose path component is the bare collection with the slash inside
the query string (`terraform/apigateway.tf:172-175`), so load the production
site and confirm the featured-projects section renders. Log in to `/admin` once,
which is the only exercise the `identity` function's real route gets.

### 6.4 Alarms to watch

Everything is in `terraform/monitoring.tf`, from `api-alarms ~> 2.1`. For the
first hour after the cut:

| Alarm | Watch for |
|---|---|
| `webbpulse-production-lambda-errors-aggregate` | Threshold is 0, so any single error on any of the four functions fires it (`terraform/monitoring.tf:54`). Expect noise from cold starts |
| `webbpulse-production-lambda-throttles-aggregate` | The concurrency-quota canary. If this fires, check section 2.6 |
| `webbpulse-production-application-errors` | Log-based, from the four `{ $.level = "ERROR" }` metric filters. Catches handled errors that `AWS/Lambda Errors` cannot see |
| `webbpulse-production-api-5xx` | The gateway's own view |
| `webbpulse-production-api-latency-p99` | Container-image cold starts are slower than zip cold starts. A p99 bump in the first minutes is expected and should settle |
| `webbpulse-production-dynamodb-throttles` | Should be unaffected. The `rate-limits` table is new and lightly used |

The threshold of 0 across four summed functions will trip more often than it did
across one, and `terraform/monitoring.tf:47-53` says so outright: it is a
starting point, not a settled answer, and is the open alarm question in section
9 of `docs/migration/pilot-split-plan.md`. Do not tune it during the release.

Tail the four function log groups:

```
/aws/lambda/webbpulse-production-content
/aws/lambda/webbpulse-production-resume
/aws/lambda/webbpulse-production-identity
/aws/lambda/webbpulse-production-public
```

All four are created by Terraform with 7 day retention
(`terraform/lambda_domains.tf:197`), so they exist from the first invoke rather
than being created lazily.

### 6.5 What actually rolls back, at each step

**After step 5.2, before 5.5.** Fully reversible and nothing is at risk.
Production still serves every path from the monolith. To undo, revert the merge
on `main` and apply; the four empty ECR repositories are destroyed. Or leave
them: four empty repositories cost nothing.

**Between 5.5 and 5.6.** The functions exist and carry the bootstrap image, the
routes point at them, and the monolith is destroyed. **This is the window with
no cheap rollback.** Forward is much faster than back: re-running
`deploy-images` is one command and a few minutes. Going back means re-adding
`module.lambda_api` and the `legacy` integration to the configuration, which is
a code change, a PR and an apply.

**After 5.6.** The ordinary rollback is a Lambda version rollback, not a
Terraform operation. `deploy-images` publishes a version per deploy
(`deploy-backend.yml:370-374`), so a bad image is reverted by pointing the
function back at the previous published version, per function.

**Reverting `default_integration`.** If the 404-on-unmatched-path behaviour
turns out to be wrong, `terraform/apigateway.tf:118` is `default_integration =
null` and naming a domain there is a one line edit, as the comment at
`terraform/apigateway.tf:110-111` says. That restores a fall-through. It is a
code change, a PR to `staging`, a promotion to `main` and an apply, so it is not
an incident-time lever. At incident time the lever is adding the missing route
key, which is the same amount of work and fixes the actual problem.

**Restoring the monolith.** The zip at
`s3://webbpulse-production-lambda-artifacts/backend/87138c18aee085b2d0fc7140b65a411a1e052c86.zip`
is **not** on its own a rollback. It is code for a function that no longer
exists. The full sequence is:

1. Re-add `module.lambda_api`, `aws_iam_role_policy.lambda_api`, the `legacy`
   integration and the two monolith route keys to the configuration. Restoring
   `terraform/lambda.tf` and `terraform/apigateway.tf` from `origin/main` at
   `45a177d` is the fastest way to get the exact text.
2. PR it, merge it, apply it. Terraform creates the function from the
   placeholder package.
3. Only then:

```bash
aws lambda update-function-code \
  --function-name webbpulse-production-api \
  --s3-bucket webbpulse-production-lambda-artifacts \
  --s3-key backend/87138c18aee085b2d0fc7140b65a411a1e052c86.zip \
  --publish
```

4. The four monolith route keys and the 21 domain keys conflict, so decide which
   surface serves what before applying step 1, not after.

That is hours, not minutes. Treat it as the disaster path, not the rollback
path. The bucket and its lifecycle rule are kept precisely so this stays
available (`terraform/lambda.tf:11-17`), and the deploy role keeps read access
to it (`terraform/iam_github_actions.tf:141-148`).

## 7. Work outside Terraform

Everything here needs the owner's agreement before it is done. None of it should
be done silently as part of the release.

**SNS subscription confirmations.** `terraform/monitoring.tf:19` subscribes
`tyler@webbpulse.com` and `tylert2610@gmail.com` to the alarm topic. Production
already has this topic from the `api-alarms ~> 1.7` era, so the two
subscriptions should already be confirmed and the module version bump should not
re-create them. **Verify by hand** before the apply that both subscriptions read
`Confirmed` rather than `PendingConfirmation` in the SNS console for account
036807648992. If the topic is re-created for any reason, both addresses get a
fresh confirmation email and **no alarm delivers to either address until the
link is clicked**, which would silently swallow exactly the alarms this release
most needs. Confirm the links in the same session as the apply.

**Lambda concurrency quota.** Section 2.6. Checking the current value is
read-only and needs no approval. **Requesting an increase is a support
interaction and needs the owner's explicit yes first.** Do not open a Service
Quotas request, a support case, or any vendor ticket without it.

**GitHub Environment variable edits.** None are required by this release
(section 2.3). Four variables become dead: `LAMBDA_FUNCTION_NAME`,
`LAMBDA_ARTIFACT_BUCKET`, `ECR_REPOSITORY_NAME`, `APP_RUNNER_SERVICE_ARN`.
Deleting them is a later tidy-up, needs the owner's agreement, and must not
happen while the rollback window is open, because `LAMBDA_FUNCTION_NAME` and
`LAMBDA_ARTIFACT_BUCKET` are two of the four values the disaster path needs.

**Repository variable gates.** `BACKEND_IMAGE_BUILD_ENABLED` and
`BACKEND_IMAGE_DEPLOY_ENABLED` are already `true` and stay `true`. With the
monolith gone they are the only path by which backend code reaches production
(`deploy-backend.yml:30-35`), so turning either off stops deploys rather than
pausing an experiment. Do not toggle them as a release control.

**Accepting the account-wide Transaction Search switch.** Section 2.8. Applying
this release changes X-Ray trace storage for every workload in account
036807648992, moves span data onto CloudWatch Logs pricing, and is not undone by
removing the Terraform. It is not a support case, so it needs no vendor ticket,
but it is an account-level change to production observability with a cost
implication and it rides along with a release whose purpose is something else.
Get the owner's explicit agreement before confirming the step 5.5 apply, or
revert PR #119 on `staging` first.

**Cross-account grants in the Artifacts account.** Section 2.5. If the
CodeArtifact domain policy or the base image repository policy has to be widened
to admit the production deploy role, that is a change to a different repository
and a different workspace, and it belongs to the owner.

**The first admin login on production.** The seeding middleware runs on the
first request to `content` and to `identity`
(`terraform/lambda_domains.tf:29-39`), and both write tables the ownership table
does not assign them. Production's admin credentials already exist in the
`webbpulse-production/app` secret from the current monolith, so no reseeding is
expected. Confirm one admin login works after the cut rather than assuming it.

## 8. What is not included

One pull request is open against `staging` at the time of writing and is **not**
part of this promotion:

| PR | Title | Branch |
|---|---|---|
| #117 | Adopt webbpulse 0.2.0 tail sampling in the domain functions | `tw-otel-0-2-0` |

PR #119, "Enable CloudWatch Transaction Search and bump aws provider to 6.46",
**was** open when this runbook was drafted and merged into `staging` on
2026-09-08 at 02:00 UTC. It is therefore inside this promotion, and section 2.8
covers what it does and the decision it asks for. If the plan in step 5.5 does
not contain the four resources listed there, the release PR was cut from a
`staging` older than `090415b` and the rest of this document's counts should be
re-checked too.

**Recommendation: promote now without #117, and follow with a second small
release.**

The reasoning is about what each release is risking. This promotion is already
the largest single change production has taken: it creates roughly 64 resources,
destroys 12 including the function that currently serves every request, replaces
the deployment mechanism, moves the AWS provider across a major version and
changes account-wide trace storage. Its risk is concentrated in the request
path, and every verification step in section 6 is aimed there.

PR #117 is an observability change. It changes how the domain functions sample
traces. It does not change routing, does not change which function serves what,
and is not needed to make the cut safe. Folding it in would mean the plan shape
in section 5.5 no longer matches what is documented here, and that a failure
during verification has more candidate causes than one.

There is a real argument the other way: promoting once with the OpenTelemetry
work included means production gets the better tracing on the day it most needs
it, during and immediately after the cut. That argument is weaker than it looks.
X-Ray active tracing is already on for all four domain functions
(`terraform/lambda_domains.tf:206`), the four log groups and the log-based error
alarm are in this release, and Transaction Search arrives with #119, so the
span pipeline is in place and only the sampling policy is deferred. The
observability floor during the cut is adequate without #117.

So: merge #117 into `staging` on its own schedule, let it apply and settle
there, and promote it as a second, small release once production has run on the
four domain functions for a day or so. Its plan will be a handful of Lambda
environment variable updates, which is a much easier thing to read on its own
than buried in this one.

A second item is deliberately deferred and is not a PR yet. The monolith's
Python source is still in the tree: `backend/app/main.py`,
`backend/app/lambda_handler.py`, `backend/app/api/v1/api.py` and
`backend/scripts/build_lambda.sh` are no longer called by CI but are what the
existing test suite builds its client from and what the route split tests prove
the four domains are a partition of. Deleting them is its own PR, and it should
wait until the rollback window has closed.

Likewise `terraform/lambda.tf`'s artifacts bucket and placeholder archive stay,
and the file says why (`terraform/lambda.tf:11-21`): the last zip in that bucket
is the rollback vehicle, the bucket costs a few cents a month, and deleting it
is not reversible. Retire it in a later PR.

---

Anything in this document marked **verify by hand** could not be confirmed from
the repository, the GitHub API or the HCP Terraform API. In particular, nothing
here was checked against live AWS: this runbook was written without AWS
credentials, so every `aws` command in it is a command to run, not a command
whose output has been seen.
