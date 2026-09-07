# Gaps in `container-image.yml@v1`, found building PR 8

PR 8 wires `deploy-backend.yml` to the org reusable workflow
`WebbPulse/.github/.github/workflows/container-image.yml@v1`. The caller is
written and every `with:` and `secrets:` key it passes matches that workflow's
declared `on.workflow_call` inputs.

The workflow as tagged `v1` cannot build this repository's images. Four gaps,
three of them blocking. They are recorded here rather than worked around,
because the fix belongs in the org workflow: forking it into this repository
would give the estate two implementations to keep in step, which is the thing
the shared workflow exists to prevent.

`v1` was read at the tag, not at the default branch. The two are byte identical
as of 2026-09-07, so nothing below is fixed on an untagged commit.

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

## Until these are fixed

The `build-images` job is wired correctly and would fail at the dependency
install, on the base image pull, or both. So it is gated on a repository
variable, `BACKEND_IMAGE_BUILD_ENABLED`, alongside the existing
`STAGING_DEPLOY_ENABLED`, and that variable is not set. The job is skipped, the
caller is committed and reviewable, and no staging deploy goes red waiting on
work in another repository.

Setting `BACKEND_IMAGE_BUILD_ENABLED` to `true` once the org workflow ships
gaps 1 to 3 is the whole of the change needed here. The first enabled run on
`staging` should push four images, one per domain, to
`webbpulse-staging/{content,resume,identity,public}` in the staging account,
each tagged `sha-<full commit sha>`, and update no function.

Nothing that serves traffic is affected either way. The monolith zip deploy
neither depends on this job nor is depended on by it.
