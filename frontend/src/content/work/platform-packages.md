---
title: Shared platform packages and modules
slug: platform-packages
summary: One typed Python package, seven TypeScript packages, 23 Terraform modules and 12 reusable GitHub workflows that every WebbPulse product builds on, so a fix to a shared pattern reaches all of them.
role: Sole software engineer (design, implementation, release process and adoption in every product)
stack: Python, uv, FastAPI, Pydantic, TypeScript, npm workspaces, Terraform, GitHub Actions, AWS CodeArtifact
period: September 2026 to October 2026
map_node: platform-packages
---

## Problem

By the time I had two backends, CarModPicker and this portfolio, each had grown its own copy of the same concerns: settings and secret loading, JSON logging, tracing, the FastAPI app factory, rate limiting, the DynamoDB access layer, password hashing and JWTs, identity, the Lambda entrypoint and the test fixtures. The frontends had the same problem. Both had written their own auth client, their own API client and a near-identical QR code encoder next to their MFA enrolment screens. The three product deploy workflows shared all eight jobs in the same order, including a byte-identical 68-line job that resolved the environment.

The copies did not just cost time. They drifted, and the drift hid bugs. CarModPicker's in-process rate limiter counted per warm Lambda, so the real limit was the configured one multiplied by however many environments were warm. The old client IP code trusted the leftmost `X-Forwarded-For` hop, so one forged header bypassed the limiter. Fixing that once, in one place, and having every product pick it up was the point of the whole exercise.

With Standupless and the Terraform control plane on the way, I wanted each new product to start from the shared answers instead of a third and fourth copy.

## Architecture

There are four repositories, one per layer.

- **`webbpulse` (Python).** One package for Python 3.13 with 18 top-level modules and 6 subpackages. The modules cover config, logging, tracing, rate limiting, DynamoDB, storage, security, composition and the Lambda entrypoint. The subpackages are `identity` (passwords, sessions, email links, TOTP, OAuth, passkeys, KMS-signed tokens and JWKS, an OAuth 2.1 server for remote MCP, the device grant and API keys), `events` (stream and queue consumers, signed webhooks), `integrations` (GitHub and Stripe), `ops`, `e2e` (a pytest plugin and post-deploy suite) and `tf`. It ships three CLIs: `webbpulse-config`, which sets keys in an environment's secret without ever printing values, `webbpulse-admin`, and `wp-tf` for my Terraform control plane. The base install depends only on Pydantic; everything else sits behind opt-in extras, so a service installs only what it uses. Nothing makes an AWS call at import time.
- **`@webbpulse/*` (TypeScript).** An npm workspace of seven ESM-only packages: `api-client`, `auth` (with React, browser and prebuilt panel entry points), `config`, `discovery`, `qrcode`, `eslint-config` and `tsconfig`. The core packages have no runtime dependencies, and React is a peer dependency used only by the React entry point.
- **`platform-modules/aws` (Terraform).** 23 modules in one repository, from building blocks such as `lambda-function`, `http-api`, `dynamodb-tables` and `sqs-queue` up to whole patterns: `identity`, `spa-frontend`, `staging-access-gate`, `app-baseline` and `github-actions-role`. There are 36 runnable examples alongside them. Each module is self-contained and never references a sibling by relative path.
- **Reusable workflows (`.github`).** 12 reusable GitHub workflows (Python and TypeScript CI, container image builds, Lambda image and per-domain deploys, SPA deploys, e2e, local-stack e2e, a check-runs gate, and the two publish workflows) plus 3 composite actions. One of the actions works out which backend domains a diff affects from each entrypoint's import closure, so CI and deploys only touch what changed.

Publishing is driven by tags. A `v*` tag on the Python or TypeScript repository runs a shared publish workflow that uploads to a private CodeArtifact domain over OIDC, so there are no personal tokens anywhere. A semver tag on the modules repository is picked up by the private module registry on my own Terraform control plane within about a minute, with no registration step. Across the four repositories that comes to about 257 semver releases in five weeks.

## Key decisions and trade-offs

**Name the consumers before hoisting.** Nothing moves into a shared package until there are concrete consumers beyond the first. That rule kept some things out on purpose. There is no shared UI kit, because the apps are on different Tailwind majors and the one primitive they shared, a button, had mismatched props. Route guards stay in each app while they are on different React Router majors. A shared library with product-specific shapes in it is worse than two copies.

**Float by default, pin as the exception.** Consumers take a floor and a major cap, such as `>=0.81.0,<1` for Python, `>=0.x <1` for TypeScript and `~> 2.39` for Terraform, so they pick up the newest compatible release at build or plan time. This is deliberate coupling. For Terraform, the place to notice a behaviour change is the next plan, and the changelog marks releases that produce no plan change. For containers, a dependency-stamp action keys the dependency layer to the newest published package version, so a rebuild actually picks it up. A manual redeploy has a `fresh-dependencies` switch, because a green deploy run is not proof that a new image shipped.

**One tag or many.** I started with one semver tag per repository. The TypeScript repository outgrew that: under a single tag, every `api-client` patch also republished `tsconfig`. So it moved to changesets with per-package versions, at the cost of CI requiring a changeset on every PR. Python and Terraform still use one tag. For Terraform that means a breaking change in any one module is a major bump for all of them, which I accept to keep consumers on a single version line.

**Small, explicit release steps.** A Python release is a one-line edit to `_version.py` plus a matching tag. I rejected deriving the version from the tag, because an sdist built outside a git checkout would then be unversioned, and CodeArtifact rejects that. For Terraform, any removed or renamed input or output anywhere is a major version.

**uv everywhere.** Python packaging is uv with a committed lockfile, third-party packages from public PyPI, and an explicit CodeArtifact index only for `webbpulse`, so a public package can never stand in for the private one. Container builds install in two layers so the dependency layer caches.

**Hardened and generic CI.** Every third-party action is pinned to a full commit SHA, permissions are least-privilege, and the public workflow repository carries nothing specific to my AWS estate. Account details, role names and domains all arrive as inputs or environment variables. GitHub's own limits shaped the design: a job that calls a reusable workflow cannot set an environment and secrets do not pass through nested workflows, which is why environment resolution is its own job and the deploy role is read from a variable.

## What I'd change

Python is still on one tag for the whole package, and as the subpackages multiply it has the same republish problem the TypeScript repository had. Per-package versioning is the next step there.

The workflows' major tag moves under callers. Inner calls pin `@v3`, so a caller pinned to an exact `v3.x.y` can still run newer code one level down. I would pin the inner calls to the release they shipped with.

The docs lag the code in places: consumer lists and workflow lists in the READMEs are incomplete. I would generate those lists from the repositories instead of maintaining them by hand.

## Links

- [webbpulse-python on GitHub](https://github.com/WebbPulse/webbpulse-python)
- [webbpulse-typescript on GitHub](https://github.com/WebbPulse/webbpulse-typescript)
- [terraform-aws-platform-modules on GitHub](https://github.com/WebbPulse/terraform-aws-platform-modules)
- [Reusable workflows on GitHub](https://github.com/WebbPulse/.github)
