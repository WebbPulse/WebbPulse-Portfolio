---
title: The AWS organisation and platform
slug: aws-organisation
summary: A multi-account AWS organisation defined entirely in Terraform, with one account per project and environment, centralised root access, shared package and image registries, and a cost kill switch that stops spend before it runs away.
role: Sole software engineer (account design, guardrails, identity, registries and cost controls)
stack: Terraform, AWS Organizations, IAM Identity Center, SCPs, CloudTrail, EventBridge, AWS Budgets, AWS Lambda, Route 53, CodeArtifact, ECR, GitHub OIDC
period: August 2026 to October 2026
map_node: aws-org
---

## Problem

Everything I run lives on AWS, and for a while that meant a handful of projects sharing too few accounts. That arrangement has two problems. A bad apply or a runaway workload in one project can reach the others, and nothing about it is reproducible: what exists is whatever someone last clicked.

I wanted three things. First, isolation by blast radius: one account per project per environment, so a mistake stays inside one account. Second, git as the definition of what exists, so adding an account or a project is a reviewed data change rather than a console session. Third, protection against the risk that actually matters for a small operation with no paying users. As the platform README puts it, with zero users a runaway bill is worse than an outage.

## Architecture

The estate is three Terraform roots, split by how much damage each one can do.

- **Organization.** Manages only AWS Organizations: the organisation, the OUs, the member accounts, centralised root access and the service control policies. It runs from the management account, because that is the only place the Organizations write APIs work.
- **Platform, "the factory".** Manages everything that turns an account into somewhere a project can deploy. That covers the per-workspace IAM run roles and read-only plan roles, the Terraform workspaces and their variables, GitHub repositories, rulesets and environments, IAM Identity Center, Route 53, CloudTrail and the cost controls. The same factory also manages Azure management groups, GCP folders and projects, and Cloudflare tokens. It is the largest root, at 62 files and 132 resource blocks across 5 local modules.
- **Artifacts.** The shared build services every project consumes and no single project owns: one CodeArtifact domain for Python and npm packages, and one ECR repository for the shared Python Lambda base image. It is built entirely from my shared Terraform modules.

The pieces fit together like this:

- **Accounts and OUs.** Six OUs: Workloads, with Prod and NonProd beneath it, plus Infrastructure, Security and Suspended. Nine member accounts sit under them: a production and a staging account for each of Portfolio, CarModPicker, the Terraform control plane and Standupless, plus one shared Artifacts account. The management account stays at the root and runs no workloads.
- **Two-pass account creation.** Organization creates an account. Platform adopts it by adding it to its ledger, which drives roles, workspaces, DNS writers and identity assignments from that one entry.
- **Identity.** IAM Identity Center has three permission sets: administrator access with one-hour sessions, read-only with four-hour sessions, and a read-only toolkit profile for automation with twelve-hour sessions. These map to three groups. Access is always assigned to groups, never to users, and it covers every account by derivation, so a new account is reachable as soon as it is in the ledger.
- **Root access.** Centralised root access is on. Member account root users have no password, access key or MFA device, and root-only tasks go through `sts:AssumeRoot` from an administrator session. A `DenyMemberRoot` SCP on the workload and infrastructure OUs denies member roots everything except those centralised tasks, including password recovery. A script proves that no member root has credentials.
- **Logging and alerts.** One multi-region CloudTrail trail for management events. A root console sign-in raises an alert through EventBridge and SNS in three regions, because AWS records the sign-in in whichever region the console happens to use.
- **Cost controls.** An organisation-wide monthly budget warns at $50 and $80, and again when the forecast passes $100. A daily budget catches spikes at $10. A critical budget at $100 actual triggers a kill switch.
- **DNS.** One Route 53 hosted zone with no delegated sub-zones. Instead, cross-account writer roles are scoped by IAM conditions to specific record names and types, and plans use read-only roles.
- **Registries.** CodeArtifact has five repositories: two that proxy public PyPI and npm, two for first-party packages, and a fan-in repository. Nothing publishes into the proxy or fan-in repositories, so a first-party name cannot be shadowed. CI gets a GitHub OIDC token, assumes a role in its own account and fetches a job-scoped token. Publisher roles use GitHub's immutable OIDC subject format, and package publishing is limited to a protected `publish` environment.
- **Applies.** All three roots run on my own Terraform control plane, each workspace federating into its own run role with the workspace id as the external id. Pull requests get speculative plans, and Organization and Platform applies wait for a manual confirmation.

## Key decisions and trade-offs

**Git defines what exists.** The defining rule for the factory is that the set of accounts, roles, workspaces, repositories and identity assignments is a pure function of the files in git. It uses no `terraform_remote_state` and no Organizations data sources. The cost is that the account map is duplicated between Organization and Platform, checked by a drift script. I accepted that because reading it from the other root could return an empty or stale answer and plan a silent no-op for a new account.

**Zero destroys as the acceptance bar.** Account resources carry `prevent_destroy`, because replacing an `aws_organizations_account` tries to close a live account. Eight plan-time guard resources check the ledgers for mistakes before anything applies.

**The factory cannot revoke its own access.** Its own run role, its Azure and GCP identities, the Identity Center instance and the root Cloudflare token are created by hand and deliberately kept out of Terraform. A cold-start runbook covers rebuilding them. A bad apply in the factory could otherwise revoke the credentials every project deploys with, including the factory's own.

**A kill switch over uptime.** When the critical budget fires, SNS invokes a Lambda that sweeps every member account and enabled region. It snapshots each resource's prior state to S3, then sets Lambda reserved concurrency to zero, throttles API Gateway stages to zero, scales ECS services to zero, stops EC2 instances, disables CloudFront distributions and finally attaches a deny-all SCP. Taking production down is a real cost. An unbounded bill is worse.

**Shared registries outside the management account.** The management account is not subject to SCPs, so nothing shared lives there. The registries sit in their own account under the same guardrails as everything else. The base image is in a single region because Lambda cannot pull an image across regions.

**Short-lived credentials everywhere.** GitHub OIDC, workspace federation, one-hour administrator sessions and job-scoped CodeArtifact tokens. There are no long-lived AWS keys in CI.

## What I'd change

The duplicated account map should become one shared file both roots read. The drift script is still a manual step, not a CI gate, and Platform has no CI of its own yet.

There is no region or service guardrail SCP. `DenyMemberRoot` and the kill switch are the only custom policies. Restricting regions would also shrink the area the kill switch has to sweep.

The kill switch fires late, because billing data can lag by about a day. It also does not handle EC2 Auto Scaling or Application Auto Scaling yet, and recovery needs the SCP detached by hand.

Adding an account still needs a hand-written provider block, because Terraform provider blocks cannot use `for_each`.

## Links

- [WebbPulse-Artifacts on GitHub](https://github.com/WebbPulse/WebbPulse-Artifacts)
