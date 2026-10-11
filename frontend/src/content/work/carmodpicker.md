---
title: CarModPicker
slug: carmodpicker
summary: A car modification tracker with a one-click Chrome extension, which I moved from App Runner and PostgreSQL to nine Lambda functions on DynamoDB without changing the public API or forcing a single password reset.
role: Sole software engineer (product, backend, frontend, extension, infrastructure and migration)
stack: Python, FastAPI, React, TypeScript, Vite, Tailwind CSS, AWS Lambda, DynamoDB, SQS, CloudFront, Terraform, WebAuthn, Chrome Extension
period: 2026
map_node: carmodpicker
---

## Problem

CarModPicker is for people who modify cars. You add your cars, plan builds as phased lists of parts, and write up progress in forum-style build logs. Underneath sits a shared parts catalog with votes, reports and price history, and you can set a price-drop alert on any part. Getting parts in is the tedious step, so there is a Chrome extension that turns a retailer's product page into a catalog entry in one click.

The engineering problem came later. The first version ran on App Runner with RDS PostgreSQL inside a VPC. That is a fine shape for a busy app and an expensive one for a small one: a database and a network that cost money around the clock whether anyone is using the site or not. I wanted it serverless, so it costs close to nothing when idle, and I wanted it built on the shared packages, Terraform modules and workflows I was writing for my other projects instead of product-local copies. CarModPicker became the first real consumer of all of them, which made it the proof that the shared wiring worked.

There were two hard constraints. The public API could not change, and no existing user could be locked out.

## Architecture

- **Frontend.** React 19, TypeScript, Vite, Tailwind CSS 4 and React Router 7, with lazy-loaded pages prerendered at build time, served from S3 behind CloudFront. Auth, configuration and the API client come from my shared `@webbpulse/*` packages.
- **API.** FastAPI on Python 3.13, split into nine domain functions: identity, users, catalog, vehicles, build lists, build logs, moderation, media and admin. Each is an arm64 Lambda container image running under the Lambda Web Adapter, behind an API Gateway HTTP API. Between them they serve 150 domain routes. Four more consumers (votes, part purge, price alerts and user delete) reuse their domain's image.
- **Boundaries.** A domain may import shared code and itself, never another domain, and a test enforces it. The gateway has explicit route keys for every path and no default integration, so an unknown path is a gateway 404 and never reaches a function.
- **Data.** DynamoDB only: 27 product tables with 45 global secondary indexes, plus six identity tables. Every table is declared once in Python and exported to a JSON file that Terraform reads, and a test fails if the two drift. Schema changes are new optional fields on the Pydantic models, so there are no migrations.
- **Async work.** Streams on four tables feed SQS. That replaced what used to be synchronous cascades and aggregates in SQL, such as vote counts and deleting a user's content.
- **Auth.** Served by the shared `webbpulse.identity` package: RS256 tokens signed in KMS, rotating refresh tokens with reuse detection, progressive lockout, TOTP with recovery codes, passkeys including passwordless sign-in, and Google and GitHub OAuth. A JWT authorizer verifies tokens once at the gateway, so functions no longer read the users table on every request.
- **Extension.** A Manifest V3 extension with only the `activeTab`, `storage` and `scripting` permissions. It runs only when you click it. It sends the page URL and rendered HTML to the API, which strips scripts and form values, then extracts the product from JSON-LD, falling back to OpenGraph tags and the DOM. You review a pre-filled form and save. Sign-in is a handoff to the web app with a state nonce and a code in the URL fragment, and the token lives in extension storage, never in cookies.
- **Everything else.** Email goes through SES, Stripe handles subscriptions, and ads load only after cookie consent. Traces go to X-Ray through OpenTelemetry and logs are structured JSON. There is no VPC and no NAT gateway.
- **Delivery.** Terraform, with staging and production in separate AWS accounts. Feature branches merge into `staging` and release PRs promote to `main`. Backend deploys use a shared workflow that rebuilds only the affected images, pins each function to an image digest and smoke-tests `/health` per domain. A shared e2e suite runs in full against staging and as a read-only smoke test against production.

## Key decisions and trade-offs

**Cut over first, then split.** The data moved to DynamoDB and production cut over on 6 September 2026, running as one FastAPI monolith on a single Lambda. The legacy VPC, database and App Runner service were destroyed straight after. Only then did I split the monolith into domains, as 33 numbered steps with one PR each. Separating the data migration from the service split meant each risky change had one thing to debug.

**Measured, not guessed.** Each domain split followed the same Terraform pattern, so I wrote the expected plan down as a formula of adds and changes per route prefix and checked five real plans against it. All five matched exactly, which made an unexpected plan easy to catch.

**No forced resets.** Moving to the shared identity package changed the token format, the user id in the subject claim and how TOTP seeds are stored. I migrated password hashes verbatim and sealed existing TOTP seeds instead of rotating them, so nobody had to reset a password or re-enrol an authenticator. Because legacy auth was deleted in the same change, the deploy was a hard cutover, and I migrated the credentials before the merge rather than after.

**Eventual consistency where it is cheap.** Moving vote aggregates onto streams makes them eventually consistent. The vote routes return counts read in the same request, so the person voting never sees a stale number.

**Fewer, broader alarms.** One errors alarm and one throttles alarm cover all nine domains, and a single DynamoDB throttle alarm replaced 25 per-table ones. Log retention dropped from 14 days to 7.

**A shared rate limiter.** An in-process limiter on Lambda multiplies the real limit by however many sandboxes are warm, so I replaced it with one fixed-window counter in DynamoDB shared by every function. It fails open if DynamoDB errors.

**Code never deploys through Terraform.** Terraform creates each function from a bootstrap image tag and then ignores the image, and CI points functions at new digests.

## What I'd change

Two write routes for listings and price history still accept requests without user auth, presumably for the extension, which could send its bearer token instead. I would close those first.

The orphan sweep is five full table scans behind an admin HTTP route with a 29 second limit. It will time out as the tables grow, and it belongs in a scheduled job.

The price-alert unsubscribe link still signs with a legacy shared key, because the recipient is not signed in. An opaque unsubscribe id per alert would let that key go.

The extension cannot refresh its own token, because the refresh token is an httpOnly cookie it cannot read, so sessions in the extension are shorter than I would like.

## Links

- [CarModPicker](https://carmodpicker.com)
- [CarModPicker Browser Companion on the Chrome Web Store](https://chromewebstore.google.com/detail/dbglgmnnfandmnacdpibkfggkadjikkg)
- [CarModPicker on GitHub](https://github.com/WebbPulse/CarModPicker)
