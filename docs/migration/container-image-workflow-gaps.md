# Gaps in `container-image.yml@v1`, found building PR 8

PR 8 wires `deploy-backend.yml` to the org reusable workflow
`WebbPulse/.github/.github/workflows/container-image.yml@v1`. The caller is
written and every `with:` and `secrets:` key it passes matches that workflow's
declared `on.workflow_call` inputs.

The workflow as originally tagged `v1` could not build this repository's images.
Five gaps, three of them blocking. They were recorded here rather than worked
around, because the fix belonged in the org workflow: forking it into this
repository would give the estate two implementations to keep in step, which is
the thing the shared workflow exists to prevent.

**All five are closed in `v1.2.0`.** Sections 1 to 5 below are kept as the
record of what was wrong and why, since each one names a failure mode that is
still worth recognising. See "Resolved in v1.2.0" at the end for what closed
each gap, how the caller uses it, and what remains open.

## 1. No BuildKit secret input. Blocking

`backend/Dockerfile` installs `webbpulse`, which is published only to
CodeArtifact, and takes the token as a secret mount:

```dockerfile
RUN --mount=type=secret,id=codeartifact_token,required=true \
    token="$(cat /run/secrets/codeartifact_token)"; \
    PIP_INDEX_URL="https://aws:${token}@..." pip install --target /deps -r requirements.txt
```

The mount is `required=true`, so a build without it fails at that line rather
than falling through to PyPI. `container-image.yml` exposes `build-args` but no
equivalent for `secrets` or `secret-envs`, both of which the underlying
`docker/build-push-action@v7` already supports. There is no way to pass the
token from the caller.

Passing it through `build-args` instead is not an option and should not become
one. A build arg is recorded in `docker history`, readable by anyone who can
pull the image, which is the exact reason the Dockerfile and
`scripts/build_image.sh` both take the trouble to use a mount.

**Asked of the org workflow:** a `secret-envs` input (or `secrets`), forwarded
to `docker/build-push-action`'s input of the same name.

## 2. No CodeArtifact login. Blocking

Even with gap 1 closed, the token has to be minted. `python-ci.yml@v1` already
does this well, with `codeartifact-domain` and `codeartifact-repository` inputs
and `codeartifact-domain-owner` as a secret, and `test-backend.yml` calls it that
way today. `container-image.yml` has no equivalent, and the step order matters:
the token must exist before the build, not before the install inside it.

Note that `codeartifact:GetAuthorizationToken` alone is not enough. The role also
needs `sts:GetServiceBearerToken` conditioned on
`sts:AWSServiceName = codeartifact.amazonaws.com`; without it the call fails with
a denial naming no CodeArtifact action at all.
`terraform/iam_github_actions.tf` already grants both.

**Asked of the org workflow:** the `python-ci.yml` CodeArtifact inputs, and a
login step that exports the token into the environment the build step reads.

## 3. ECR login covers only the caller's own registry. Blocking

The Dockerfile's `FROM` is the shared base image in the Artifacts account:

```
432410731887.dkr.ecr.us-west-2.amazonaws.com/webbpulse/python-lambda-base@sha256:b5298b...
```

`container-image.yml` runs `aws-actions/amazon-ecr-login` with no `registries:`
input, which authenticates the caller's own account registry and no other. The
pull of the base image then fails with a 401 from a registry Docker holds no
credential for.

This is not an IAM problem and will not present as one.
`terraform/iam_github_actions.tf` grants the deploy role `ecr:BatchGetImage`,
`ecr:DescribeImages` and `ecr:GetDownloadUrlForLayer` on that repository
already, and the Artifacts account grants the other half on the repository
itself. The permission is there; the Docker credential for that host is not.

**Asked of the org workflow:** a `registry-accounts` input passed through to
`amazon-ecr-login`'s `registries`, so a build can pull a base image from a
second account.

## 4. No existing-tag guard on an IMMUTABLE repository. Not blocking, but it will bite

`terraform/ecr.tf` creates the four repositories with `IMMUTABLE` tags, and the
workflow tags solely `sha-<full git sha>`, derived from `GITHUB_SHA`. A rerun of
a green commit therefore pushes a tag that already exists.

Whether that fails depends on the bytes. If the rebuild is reproducible the
digest is unchanged and ECR treats re-tagging the same manifest as a no-op, so
the push succeeds. If anything moved (a transitive dependency resolving
differently, or a base image tag rather than a digest) the digest differs, ECR
rejects the `PutImage` with `ImageTagAlreadyExistsException`, and the job fails
for a reason that has nothing to do with the commit under test.

Re-running a workflow is a routine thing to do, so this is a real trap rather
than a theoretical one. The plan's section 4 leans on exactly this reproducibility
when it recommends rebuild-per-environment over cross-account copy, and it names
the pinning that has to hold for that to be honest.

**Asked of the org workflow:** a check before the build for whether the tag
already resolves, skipping the push and emitting the existing digest as the
outputs if so. It should use `aws ecr batch-get-image` rather than
`describe-images`: the deploy role has `ecr:BatchGetImage` on the domain
repositories but `ecr:DescribeImages` only on the shared base image repository,
and the workflow's own manifest verification step already uses
`batch-get-image` for that reason.

## 5. Per-domain outputs cannot be read back from a matrix. Caller side, not a workflow gap

Worth writing down because it shapes what PR 8 could deliver and what PR 10 has
to do.

`container-image.yml` returns `image-uri` pinned by digest, which is the right
output and is what `function-image-map` should eventually carry. But a matrix of
reusable workflow calls collapses to a single `needs` entry whose `outputs` hold
whichever leg finished last, and a job with `uses:` cannot carry `steps:`, so the
caller has nowhere to capture each leg's value.

PR 8 therefore writes the map keyed by the immutable tag rather than the digest.
The tag is `sha-<full git sha>` for all four domains, it is immutable, and PR 10
resolves it to a digest at deploy time. If digest pinning is wanted end to end,
the way to get it is for the org workflow to write each leg's URI to a uniquely
named artifact that an aggregating job downloads, which is a change to
`container-image.yml` and not something the caller can arrange.

## Resolved in v1.2.0

`WebbPulse/.github` released `v1.2.0` on 2026-09-07 (commit `9643c82`, which the
floating `v1` tag now points at). It closes gaps 1 to 5. `deploy-backend.yml`
passes the new inputs, so the caller no longer needs a workaround for any of
them.

| Gap | Closed by | How the caller uses it |
| --- | --- | --- |
| 1. No BuildKit secret input | The token is exported to the job environment and handed to `docker/build-push-action` through `secret-envs`, which names the variable rather than carrying the value. The mount id is the `codeartifact-secret-id` input, default `codeartifact_token`. | Nothing to pass. The default id already matches the Dockerfile's `RUN --mount=type=secret,id=codeartifact_token`, so the caller leaves it unset. It is still never a build arg. |
| 2. No CodeArtifact login | `codeartifact-domain`, `codeartifact-domain-owner` and `codeartifact-repository` inputs, with a validation step that fails clearly when the domain is set and the other two are not, and a mint step that runs after the credentials step and before the build. | `codeartifact-domain: webbpulse`, `codeartifact-domain-owner: ${{ vars.CODEARTIFACT_DOMAIN_OWNER }}`, `codeartifact-repository: python`. |
| 3. ECR login covers only the caller's own registry | `additional-ecr-registries`, passed through to `amazon-ecr-login`'s `registries`. The caller's own account id is prepended by the workflow, because `amazon-ecr-login` stops assuming the default registry once a list is given. | `additional-ecr-registries: "432410731887"`, the Artifacts account holding `webbpulse/python-lambda-base`. |
| 4. No existing-tag guard on an IMMUTABLE repository | `skip-if-tag-exists`, default `true`. It resolves the tag with `aws ecr batch-get-image` (not `describe-images`, for the permission reason this document gave) and, when the tag is already there, skips the build and emits the existing digest as the outputs. | Nothing to pass. The default is the wanted behaviour, and a rerun of a green commit is now green. |
| 5. Per-domain outputs cannot be read back from a matrix | `upload-manifest-artifact`, which writes one JSON file per leg as an artifact named `image-<sanitised repository>-<tag>` carrying the repository, tag, digest and digest pinned URI. | `upload-manifest-artifact: true`. The `image-map` job downloads `image-*` with `merge-multiple: true` and assembles the map from the manifests. |

The concrete consequence for this repository is that `image-map` is now keyed by
**digest** rather than by tag. Where PR 8 originally wrote
`webbpulse-<env>/<domain>:sha-<sha>` with no registry host, it now writes the
`image_uri` the reusable workflow returns, `<registry>/<repository>@sha256:...`,
and uploads the whole object as a `function-image-map` artifact for PR 10 to
consume. Gap 5 is what made the tag-keyed form necessary, and it is gone.

### Still open

- **`amazon-ecr-login`'s `registry` output is unset with multiple registries.**
  The action documents that it sets `registry` only when it logs in to exactly
  one, and passing `additional-ecr-registries` always means more than one. The
  workflow therefore derives the caller's own registry host from
  `sts get-caller-identity` plus `aws-region` rather than reading that output.
  Correct, and worth knowing: the host in an `image_uri` comes from STS, so an
  `aws-region` that disagrees with where the repository actually lives would
  produce a URI that resolves to nothing rather than an error at push time.
- **`codeartifact-domain-owner` is an input here, not a secret.** `python-ci.yml`
  takes it as a secret and `test-backend.yml` passes it that way, so the two
  workflows are configured differently for the same value. The org repository's
  reasoning is that an account id is an identifier rather than a credential, and
  a matrix caller usually already holds it in a repository variable, which is
  the case here: `vars.CODEARTIFACT_DOMAIN_OWNER`. Not a problem, but do not
  copy a `secrets:` line from one caller to the other.
- **Unverified end to end.** No enabled run of `build-images` has happened. The
  v1.2.0 author flagged this, and it is the reason the first run on `staging`
  after `BACKEND_IMAGE_BUILD_ENABLED` is set is worth watching rather than
  assuming. The failure modes that survive review are the ones this document has
  described twice already: the base image pull presenting as a 401 rather than a
  denial, and `sts:GetServiceBearerToken` presenting as a denial that names no
  CodeArtifact action.
- **The function names are not yet real.** PR 9 has not landed on `staging`, so
  `terraform/lambda.tf` still declares only the monolith `${local.prefix}-api`.
  `image-map` keys the map with `webbpulse-<env>-<domain>`, which is what
  `docs/migration/pilot-split-plan.md` section 3.3 specifies
  (`function_name = "${local.prefix}-${each.key}"`). If PR 9 lands with a
  different naming, this is the one place that has to follow it.

## Until the gate is set

The `build-images` job is wired to v1.2.0 and every gap that blocked it is
closed, but it stays gated on the repository variable
`BACKEND_IMAGE_BUILD_ENABLED` alongside the existing `STAGING_DEPLOY_ENABLED`,
so the first enabled run is a deliberate act rather than a side effect of a
merge. Setting it to `true` is the whole of the remaining change here.

The first enabled run on `staging` should push four images, one per domain, to
`webbpulse-staging/{content,resume,identity,public}` in the staging account,
each tagged `sha-<full commit sha>`, write the digest pinned map to the job
summary, upload it as `function-image-map`, and update no function.

Nothing that serves traffic is affected either way. The monolith zip deploy
neither depends on this job nor is depended on by it.
