---
title: Standupless
slug: standupless
summary: A multi-tenant issue tracker in the shape of Linear, with GitHub pull requests that move issues on their own, a 151-tool MCP server, a CLI, Slack and Discord apps, and a desktop client, which I build and use to track all of my own work.
role: Sole software engineer (product, backend, frontend, integrations and infrastructure)
stack: Python, FastAPI, React, TypeScript, DynamoDB, AWS Lambda, SQS, CloudFront, Terraform, GitHub App, MCP, Electron, Stripe
period: September 2026 to October 2026
map_node: standupless
---

## Problem

A standup meeting mostly exists to answer "what is everyone doing?". If the issue tracker already knows, because pull requests update it and every tool can write to it, the meeting has nothing left to do. Standupless is an issue tracker for software teams built around that idea: file issues, plan cycles, group work into projects and link pull requests, then check progress in the app rather than in a meeting.

It is also the system of record for everything I build. Every repository, release and infrastructure change across my projects is tracked as a Standupless issue in production, so friction is something I hit daily and file as a bug.

Linear is the reference for the UX and the vocabulary. Teams that already know Linear should not have to learn a second set of nouns for the same ideas.

## Architecture

- **Backend.** FastAPI on Python 3.13, split into nine domains (identity, workspaces, teams, issues, discussion, views, planning, integrations and admin). Each one is its own arm64 Lambda container image, built from one Dockerfile and served behind an API Gateway HTTP API. The backend has 294 route handlers. A single registry declares the domains, and tests fail if one domain imports another, or if the tables a domain declares differ from the tables Terraform grants it.
- **Composition.** One root mounts every domain in a single process for local development and the merged OpenAPI document. The other builds one app per deployed function. A test asserts the two are the same set of routes, so nothing can work locally and be missing in production.
- **Data.** 22 DynamoDB tables. Similar entities share a table and are told apart by a sort-key prefix, using named attributes rather than a generic `PK`/`SK` scheme. Code that touches a table outside its domain's declared set fails locally, the same way IAM would refuse it in production.
- **Async work.** DynamoDB Streams and SQS drive consumers for rollups, notifications, search indexing, GitHub events, outbound webhooks, exports and team deletion. Every queue has a dead-letter queue.
- **Frontend.** React 19, React Router 7, Vite and Tailwind 4, with a TipTap editor for markdown. It is a prerendered single-page app on S3 and CloudFront.
- **Identity.** Served by my shared `webbpulse.identity` package: RS256 JWTs, Google and GitHub sign-in, and passkeys, including as a second factor. Production verifies tokens with API Gateway's native JWT authorizer.
- **GitHub App.** Webhooks are checked against their HMAC signature before the body is parsed, deduplicated on the delivery id, acknowledged with a 202 and queued. Nothing calls GitHub inside the webhook request. Issue keys are matched against each team's own prefix in branch names, PR titles, PR bodies and commits. `Fixes`, `Closes` and `Resolves` only count in the title or body, so a rebase cannot close an issue twice. Results go back as a PR comment and a check run. Two-way issue sync and release tracking build on the same pipeline.
- **MCP server.** A remote HTTP MCP server inside the integrations function. It has 151 tools, so anything you can do in the app, an AI assistant can do through MCP. The identity domain doubles as its OAuth authorization server: authorization code with PKCE S256 only, dynamic client registration, consent per client and per workspace, revocation from a Connected apps page, and every token bound to one workspace.
- **Other clients.** A CLI on PyPI (`standupless-cli`) that keeps its API key in the OS keyring. Slack and Discord apps with slash commands, link unfurls and signature verification. An Electron desktop app that auto-updates from GitHub releases.
- **Billing.** Stripe per-seat Checkout and the customer portal. The webhook is the only writer of a workspace's plan.
- **Delivery.** One Terraform root built almost entirely from my shared module registry (17 distinct modules), applied by my own Terraform control plane. Staging applies automatically and production waits for a manual confirm. Every merge deploys only the affected domains, and an e2e suite runs in full on staging and as a read-only smoke test on production. That includes real GitHub sync against a dedicated public test repository.

## Key decisions and trade-offs

**Tenancy by construction.** Every partition key starts with the workspace id and every repository method takes `workspace_id` first, so a query cannot cross workspaces without anyone needing to remember a filter. A single authorization dependency decides every request and fails closed. A non-member gets a 404 rather than a 403, so nobody can probe for a workspace's existence. JWTs, API keys and MCP tokens all resolve to the same authorization context. An API key's access is its scopes intersected with its creator's current role, re-read on every request.

**Gap-tolerant issue keys.** Keys like `ABC-123` come from a per-team counter incremented with a single atomic `ADD`. A crash between the increment and the write can leave a gap, and gaps are never renumbered. That trade buys allocation without a transaction.

**Search on DynamoDB.** Search is an inverted index kept up to date from the issues stream, with caps on terms per issue and postings per term. There is no relevance ranking, and a common term in a large team is a hot partition. I accepted both to keep search inside the same tables, streams and bill as everything else.

**Deterministic features only.** The standup digest, similar-issue detection, CSV import and release notes are all deterministic. Nothing is summarised or classified by a model. The output is predictable, testable and free to run.

**Linear's nouns, renamed early.** My first names were one step off Linear's: my "project" meant what Linear calls a team, and it collided with Linear's own "project". I renamed project to team first and milestone to project second, because doing it in the other order would have merged the two concepts. There is no translation layer, so the API says what the UI says.

**One GitHub App per environment.** A shared App would let a staging delivery move a production issue. The App is created from inside the web app through GitHub's manifest flow, and its credentials go straight into the environment's secret, because a private key that passed through a build log would have to be treated as compromised.

**Fix the platform, not the product.** When Standupless needed something reusable (an OAuth server, API keys, HMAC verification, an idempotency store), it went into my shared packages and modules rather than a product-local workaround.

## What I'd change

Search is the obvious next limit. Without ranking or a way to spread hot terms, it will degrade as teams grow, and it is the piece I would move to a dedicated index first.

The activity history is kept forever, which is right for audit but grows without bound on long-lived issues. I would add an archive tier.

Adding a domain to a live environment takes two Terraform runs, and a fresh account takes three. I would like that to be one.

The desktop builds ship unsigned, so macOS blocks the first launch and auto-update does not work there. Fixing that needs a paid Apple signing membership.

## Links

- [standupless.dev](https://standupless.dev)
- [Standupless on GitHub](https://github.com/WebbPulse/Standupless)
- [standupless-cli on PyPI](https://pypi.org/project/standupless-cli/)
