---
title: The Terraform control plane
slug: webbpulse-terraform
summary: A serverless Terraform control plane I built to replace HCP Terraform for every WebbPulse workspace, with HCP-compatible runs, a private registry and a Go provider that manages the plane as code.
role: Sole software engineer (design, backend, runner, frontend, provider and cutover)
stack: Python, FastAPI, AWS Lambda, Step Functions, ECS Fargate, DynamoDB, S3, React, TypeScript, Go, Terraform
period: September 2026 to October 2026
map_node: control-plane
---

## Problem

Every piece of WebbPulse infrastructure is Terraform, and for a long time all of it ran through HCP Terraform. That stopped working on cost. HCP bills per managed resource, the free tier covers 500, and the organisation manages roughly 3,900. The free tier had also dropped to 50 applies a month, while a single busy staging workspace was doing 80 applies in 30 days. I looked at Scalr and rejected it for its run quota.

So I built my own control plane. The goals were specific: serverless and close to zero cost when idle, close enough to HCP that the workflow did not change, and built from the same shared packages and modules as the rest of my projects.

## Architecture

The plane is a FastAPI backend, a React single-page app and a Fargate runner, wired together by Step Functions.

- **API.** FastAPI on Python 3.13, packaged as Lambda container images behind an API Gateway HTTP API. One Dockerfile builds four domain functions (`workspaces`, `runs`, `github`, `registry`) from a build argument. A test asserts that the single-process app used locally is exactly the union of the four deployed apps, so the split can never drift.
- **Data.** Workspaces, configuration versions and runs live in DynamoDB with prefixed ULID ids (`ws-`, `cv-`, `run-`). State lives in a versioned, KMS-encrypted S3 bucket at one key per workspace, and state history is just the S3 object versions.
- **Locking.** Terraform's native S3 lockfile (`use_lockfile = true`), which sets Terraform 1.11 as the floor. CLI locks write the same `.tflock` object with `If-None-Match: *`, so the plane and a local CLI agree on who holds the lock.
- **Runs.** Each run is one Step Functions execution with 22 states. The happy path is acquire a semaphore, plan, check the outcome, wait for confirmation, apply, record the result and release the semaphore. Plan and apply are each an ECS task started with `waitForTaskToken`. Runs on a workspace queue behind each other, and concurrency across the plane is a DynamoDB semaphore capped at 25, which is what the Fargate vCPU quota supports at one vCPU per runner.
- **Runner.** An arm64 image with pinned, checksummed Terraform and OpenTofu binaries. It proves who it is by sending a signed STS `GetCallerIdentity` request, which the API replays to STS and cross-checks against `ecs:DescribeTasks`. It then fetches a bundle of presigned URLs, decrypted variables and vended credentials, streams redacted output to CloudWatch, uploads the plan and log, and heartbeats every minute. The engine runs as an unprivileged user, so the code being planned cannot read the runner's tokens or forge the change counts it reports. An end-to-end test checks exactly that.
- **Credentials.** The `runs` function assumes a vending role, which assumes the workspace's run role with the workspace id as the external id. Plans get a `ReadOnlyAccess` session policy. Credentials reach Terraform as `credential_process` profiles that refresh ten minutes before expiry, so a long apply can outlive the one-hour limit on chained roles. For new accounts there is a "Quick setup" modelled on HCP dynamic credentials: a CloudFormation quick-create link builds the role, a custom resource reports back with a one-time token, and the workspace only switches once a plan-only verification run passes. For Google and Azure, the plane acts as its own OIDC issuer and signs tokens with a KMS key.
- **GitHub.** One GitHub App per environment. A push starts a run that waits for confirmation, a same-repo pull request starts a plan-only run, and results come back as per-workspace check runs, one aggregate check and a single PR comment.
- **Registry and CLI compatibility.** A private module and provider registry, plus a `tfe.v2` API surface, so the stock `terraform` CLI can log in over OAuth with PKCE and use a `cloud {}` block for remote plans, applies and state commands. The real CLI exercises this against staging in CI.
- **Provider.** `terraform-provider-webbpulse`, written in Go on the Plugin Framework, has 7 resources and 7 data sources. The platform's workspace factory uses it to manage every other workspace, so the plane's own configuration is code too.
- **CLI.** `wp-tf`, part of my shared Python package, has nine subcommands for planning, applying, confirming and tailing logs,.

## Key decisions and trade-offs

**HCP's UX as the reference, and nothing else of it.** The information architecture, run vocabulary and flows follow HCP Terraform so nobody has to relearn them. Branding does not. I also copied behaviour where it mattered: safe workspace delete, per-workspace auto-apply, speculative plans and remote state sharing.

**The plane applies itself.** Production manages the staging plane, and staging never manages itself. The obvious risk is a bad apply that breaks the thing that would deploy the fix, so there is a break-glass script that plans and applies against the same S3 state without going through the plane.

**Staging auto-applies, production waits.** Staging workspaces apply on their own. Production holds every apply for an explicit confirm, with a 24 hour window. Auto-apply is per workspace and off by default.

**A byte-for-byte cutover.** I wrote a dedicated cutover tool. It copied each workspace's state from HCP to S3 byte for byte, verified lineage and serial by reading it back, compared variable shapes without reading their values, and could push state back to HCP to roll back. Workspaces moved busiest first, starting with a CarModPicker staging pilot and finishing with the platform factory. All 11 moved, the final HCP state was archived with checksums, and then I deleted the tool, the HCP workspaces, the variable sets, the projects and the HCP OIDC provider in every AWS account.

**Accepted risks, written down.** Pull request plans can read the target account and decrypted variables, as they can on HCP. Plans never assume writer roles. Sensitive variables are sealed with AES-256-GCM using a per-workspace derived key, and the run bundle is the only place they are decrypted.

**A fixed cap instead of a scheduler.** 25 concurrent runs is a ceiling set by the Fargate quota, not a design target. Anything past it queues.

## What I'd change

The CLI compatibility layer has rough edges I would close first. You cannot create a workspace from a `cloud {}` block, and without tags only name-based selection works. There is also a short window after a plan finishes, before the task token lands on the run row, when a confirm returns 409.

The module registry only supports modules at the repository root, and deleting a tag does not unpublish a version. GitHub also skips push events when more than three tags arrive at once, which is why a manual resync route exists. I would rather handle that with a periodic reconcile.

## Links

- [WebbPulse-Terraform on GitHub](https://github.com/WebbPulse/WebbPulse-Terraform)
- [terraform-provider-webbpulse on GitHub](https://github.com/WebbPulse/terraform-provider-webbpulse)
- [webbpulse-terraform-staging-e2e on GitHub](https://github.com/WebbPulse/webbpulse-terraform-staging-e2e)
- [webbpulse-python (home of wp-tf) on GitHub](https://github.com/WebbPulse/webbpulse-python)
