# Production promotion runbook

How the identity migration that lives on `staging` reaches `main`, which is
production.

This is the ordered checklist for one specific promotion: merging `staging` into
`main` and applying it to the production workspace. It assumes
`docs/identity-cutover.md` has been read, because that document explains what
the cutover is and why each script exists. This one is narrower: the order, the
exact commands, the plan shapes to expect, and the gates that stop the
promotion.

**Nothing in this document is authorised to run itself.** Every merge, every
apply and every write below is an owner decision.

## State at the time of writing, 2026-09-10

Verified against the live accounts rather than assumed.

| Thing | Staging (621554169154) | Production (036807648992) |
| --- | --- | --- |
| Branch | `staging`, 65 commits ahead of `main` | `main` |
| HCP workspace | `ws-5SsqJj33we9fQJGY` | `ws-JpNLUhFzVCzMDgAN` |
| `identity_jwt_mode` | `gate` | unset, so `off` by default |
| Identity stack | applied | none: no KMS signing key, no identity tables |
| Identity tables | present | absent, `aws dynamodb list-tables` shows 11 non-identity tables |
| SES identities | `staging.webbpulse.com`, DKIM verified | none |
| SES sandbox | in sandbox | in sandbox, `ProductionAccessEnabled: false` |
| Discovery document | `200` at the staging API host | `404` at `https://api.webbpulse.com/api/auth/.well-known/openid-configuration` |
| Gateway authorizers | gate REQUEST authorizer | none, `get-authorizers` returns `[]` |
| Frontend `AUTH_MODE` | `identity` on the staging GitHub Environment | unset on production, so `bearer` |
| Legacy users | synthetic | **one real administrator row with `hashed_password`** |

The four per-domain Lambdas already exist in production
(`webbpulse-production-{public,content,resume,identity}`) and all four ECR
repositories already hold the image tagged
`sha-287cfca39eef5110be256fa1714878c3c87fd39a`, which is the value of
`bootstrap_image_tag` on the production workspace today. The production identity
function exists but carries none of the `IDENTITY_*` environment variables, so it
serves nothing under `/api/auth`. That is consistent with the `404` above.

## Blockers, to be settled before anything is merged

### 1. The DMARC record would overwrite production's own, and this is a hard no-go

`terraform/ses.tf` creates `aws_route53_record.ses_dmarc` at
`_dmarc.${local.domain}`. Its own comment states the resource is staging-only
"by construction", but that claim does not hold. The gate is
`local.custom_domain_count`, which is
`var.staging_profile == "full" && var.route53_zone_id != null`, and **both are
true in production**. `local.domain` in production is `webbpulse.com`, so the
resource resolves to `_dmarc.webbpulse.com`.

That name is already in use. Live DNS today:

```
$ dig +short TXT _dmarc.webbpulse.com @1.1.1.1
"v=DMARC1; p=none; rua=mailto:tyler@webbpulse.com"
```

Applying `staging` to production as it stands replaces that with
`v=DMARC1; p=quarantine; adkim=s; aspf=s`. Two consequences, and the second is
the serious one:

- The `rua` is dropped, so aggregate reports stop arriving.
- The policy moves from monitor-only to `p=quarantine` with `adkim=s` on a
  domain whose real mail is Google Workspace (`MX 1 smtp.google.com`, apex SPF
  `v=spf1 include:_spf.google.com ~all`). Google Workspace mail signs with
  `d=webbpulse.com`, so strict DKIM alignment should pass, but this is the
  production mail domain for a real mailbox and the failure mode is legitimate
  mail landing in spam. `ses.tf`'s own header argues at length that `p=none` is
  correct for exactly this domain and then, through a gate that does not do what
  the comment says, changes it.

**Do not promote until this is fixed.** The fix is a one-line change in
`ses.tf`, gating that single resource on the environment rather than on custom
domains:

```hcl
resource "aws_route53_record" "ses_dmarc" {
  count    = var.environment == "staging" ? local.custom_domain_count : 0
  ...
}
```

Confirm the fix with a production plan showing no change to
`aws_route53_record.ses_dmarc`. This needs its own pull request against
`staging`, reviewed and merged, before the promotion branch is cut.

### 2. SES is in the production sandbox, which limits email to verified addresses

`aws sesv2 get-account` in 036807648992 returns `ProductionAccessEnabled: false`,
a 200 message daily cap and a 1 message per second rate. In the sandbox SES
delivers only to addresses or domains that are themselves verified in the
account.

So after promotion, email verification and password reset links will reach the
administrator's own address only if that address is separately verified as an
SES identity in the production account. Every other recipient gets a rejected
send.

This is a limitation to accept knowingly, not a blocker: Portfolio is a single
administrator product whose one account is seeded, and
`IDENTITY_REGISTRATION_ENABLED` is `"false"`, so there is no self-service signup
that would mail a stranger. The administrator can sign in with a password, with
a passkey once enrolled, or through Google or GitHub, and none of those paths
sends mail.

**Leaving the sandbox requires a support case, which is an owner decision and is
deliberately not opened here.** If the owner wants reset-by-email to work for
arbitrary addresses, request production SES access for 036807648992 in us-west-2
first and treat this runbook as blocked on it. Otherwise proceed and verify the
administrator's address as an SES email identity as a follow-up.

### 3. Passkeys and OAuth are off or narrowed in production by derivation

Not a blocker, but it changes what "verified" means at the end.
`terraform/identity.tf` derives both passkey switches from the environment:

```hcl
passkeys_enabled      = var.passkeys_enabled != null ? var.passkeys_enabled : var.environment != "production"
passkeys_passwordless = var.passkeys_passwordless != null ? var.passkeys_passwordless : var.environment != "production"
```

So in production both resolve to `false` unless an HCP variable overrides them,
and the passkey routes are not declared. Passkey sign-in cannot be part of the
production verification until `passkeys_enabled` is set to `true` on the
workspace, which is a separate decision after the promotion holds.

OAuth is live in production by contrast: all four `oauth_*` variables are
already set on `ws-JpNLUhFzVCzMDgAN`, so the Google and GitHub providers are
advertised as soon as the identity function serves. Confirm with the owner that
the two OAuth apps carry
`https://api.webbpulse.com/api/auth/oauth/callback` as a registered redirect URI
before step 9, because that string is compared by exact equality and a mismatch
fails the callback rather than the authorize.

## HCP variables to add to the production workspace

Read from `ws-JpNLUhFzVCzMDgAN` on 2026-09-10. Present today:
`admin_email`, `admin_password`, `admin_username`, `bootstrap_image_tag`,
`manage_spans_log_group`, the four `oauth_*`, `route53_write_role_arn`,
`route53_zone_id`, and the three `TFC_AWS_*` environment variables.

Nothing has to be added for the first apply. Everything the identity stack needs
in production either already exists or has a correct default. The table below is
the full set of variables that differ from staging, with the production answer
for each.

| Variable | Add to production? | Value | Why |
| --- | --- | --- | --- |
| `identity_jwt_mode` | **Yes, but only at step 10** | `native` | Absent means `off`, which is exactly right for the first apply. Adding it as `native` before the identity function serves discovery fails the apply. |
| `environment` | No | n/a | Staging sets it explicitly; production relies on the declared default, which is `production` in `terraform/variables.tf` and is validated against the two allowed values. |
| `passkeys_enabled` | Optional, later | `true` to turn passkeys on | Derived `false` in production. Leave unset for the promotion. |
| `passkeys_passwordless` | Optional, later | `true` | Derived `false`. Leave unset; turning it on makes a passkey a way in with no password. |
| `identity_rp_name` | No | n/a | Defaults to `WebbPulse Portfolio`, which is correct. |
| `staging_access_gate`, `staging_access_users`, `staging_profile` | No | n/a | Staging-only. `staging_profile` must stay at its default `full` in production for custom domains, which is what `local.custom_domains_enabled` reads. |
| `gcp_project_id`, `ARM_SUBSCRIPTION_ID`, `TFC_AZURE_*`, `TFC_GCP_*` | No | n/a | Staging multi-cloud only. |

The three `admin_*` sensitive variables already hold the real production
administrator credentials and must not be touched: they feed the
`webbpulse-production/app` secret and the seeder, and changing `admin_password`
here rewrites the credential the migration is about to copy.

### Secret keys

The `webbpulse-production/app` secret already exists
(`arn:aws:secretsmanager:us-west-2:036807648992:secret:webbpulse-production/app-XGfAme`,
last changed 2026-09-06). After promotion `terraform/db.tf` adds two keys to
that JSON blob, matching staging:

| Key | Source | Present in production today |
| --- | --- | --- |
| `SECRET_KEY` | `random_password.secret_key` | yes |
| `ADMIN_USERNAME` | `var.admin_username` | yes |
| `ADMIN_PASSWORD` | `var.admin_password` | yes |
| `ADMIN_EMAIL` | `var.admin_email` | yes |
| `OAUTH_GOOGLE_CLIENT_SECRET` | `var.oauth_google_client_secret` | **added by the promotion apply** |
| `OAUTH_GITHUB_CLIENT_SECRET` | `var.oauth_github_client_secret` | **added by the promotion apply** |

Both source variables already exist on the workspace, so the apply fills them
rather than writing empty strings. The key names are upper case on both sides
and the case is load bearing.

Never read the secret's value to check this. Verify the shape from the plan and
from behaviour, which is what step 9 does.

## Why this is two applies and not one

`identity_jwt_mode = "native"` makes the platform API module create an
`aws_apigatewayv2_authorizer` of type JWT. API Gateway's `CreateAuthorizer` call
**synchronously fetches**
`https://api.webbpulse.com/api/auth/.well-known/openid-configuration` from
outside AWS and then the JWKS it names, at create time. Today that URL returns
`404`, which is confirmed above.

So the order is forced:

1. **First apply, mode `off`.** Creates the KMS signing key, the ten identity
   tables, the IAM grants, the SES identity and DKIM records, the new route keys,
   and sets the `IDENTITY_*` environment variables on the identity function. No
   authorizer is created. Nothing is enforced at the gateway, and the
   applications still verify tokens themselves in every mode.
2. **Deploy the backend image**, so the identity function actually runs code
   that serves discovery and JWKS.
3. **Second apply, mode `native`.** Now `CreateAuthorizer` can fetch the two
   documents, and the marked routes move to `authorization_type = JWT`. Those
   routes are replaced rather than updated, because the platform module keeps
   them in a separate resource so the `.well-known` routes exist before the
   authorizer and the protected routes after it.

Attempting both in one apply fails the second half and leaves the workspace
mid-apply. The variable's own description says the same thing.

### The bootstrap image tag

`var.bootstrap_image_tag` seeds `image_uri` for each per-domain function and is
validated against `^sha-[0-9a-f]{40}$`. Lambda pulls and optimises the image when
it **creates** the function, so a tag that does not resolve fails the create.

In this promotion all four production functions already exist, so the seed is
not on the create path and the current value is fine. It still matters for one
reason: the ECR lifecycle policy on these repositories expires untagged images
after one day and keeps only the last ten tagged `sha-` images. The tag
currently on the workspace,
`sha-287cfca39eef5110be256fa1714878c3c87fd39a`, was pushed 2026-09-07 and is
still present in all four repositories, verified. If any function is ever
replaced, refresh `bootstrap_image_tag` to the current head sha first.

`image_uri` is on the module's `ignore_changes` list, so the deploy step's
`UpdateFunctionCode` is not undone by the next plan.

## The checklist

### Step 0. Gates before anything

- [ ] The DMARC fix from blocker 1 is merged to `staging` and a production plan
      shows no change to `aws_route53_record.ses_dmarc`.
- [ ] The owner has decided on the SES sandbox, blocker 2: either accept the
      limitation or request production access first.
- [ ] Staging has been confirmed clear per `docs/identity-cutover.md`, meaning
      the legacy column there is cleared and identity sign-in works.
- [ ] The owner has confirmed the Google and GitHub OAuth apps carry
      `https://api.webbpulse.com/api/auth/oauth/callback`.
- [ ] The owner is present. **Every commit to `main` auto-deploys**, so the
      merge in step 2 is a release.

**No-go if any box is unchecked.**

### Step 1. Take a restore point

```bash
cd /path/to/WebbPulse-Portfolio
git fetch origin
git rev-parse origin/main
```

Record that sha. It is the revert target in the rollback section, and it is the
only cheap part of the rollback.

Snapshot the one row that matters, so a mistake in step 7 is recoverable:

```bash
AWS_PROFILE=Portfolio-Production/AdministratorAccess \
  aws dynamodb scan --region us-west-2 \
    --table-name webbpulse-production-users \
    > ~/prod-users-preflight.json
```

The table holds exactly one item, verified by a `--select COUNT` scan. That file
contains a real bcrypt hash: keep it off shared storage and delete it when the
promotion holds.

### Step 2. Confirm production is on mode off, then merge

`identity_jwt_mode` must be **absent** from `ws-JpNLUhFzVCzMDgAN`, which is the
state today. Re-verify rather than trusting this document:

```bash
T=$(jq -r '.credentials["app.terraform.io"].token' ~/.terraform.d/credentials.tfrc.json)
curl -s -H "Authorization: Bearer $T" \
  https://app.terraform.io/api/v2/workspaces/ws-JpNLUhFzVCzMDgAN/vars \
  | jq -r '.data[].attributes | select(.key=="identity_jwt_mode") | .value'
```

Expect no output. **If it prints `native`, stop:** the merge would trigger a run
that fails at `CreateAuthorizer`.

Then open the promotion pull request from `staging` into `main` and merge it.
Merging is an owner action.

### Step 3. Watch the first run, mode off

The merge queues a run on `ws-JpNLUhFzVCzMDgAN`. No workspace auto-applies, so
confirm the apply through the UI or the API after reading the plan.

```bash
T=$(jq -r '.credentials["app.terraform.io"].token' ~/.terraform.d/credentials.tfrc.json)
curl -s -H "Authorization: Bearer $T" \
  "https://app.terraform.io/api/v2/workspaces/ws-JpNLUhFzVCzMDgAN/runs?page[size]=1" \
  | jq -r '.data[0] | {id, status: .attributes.status, message: .attributes.message}'
```

**What the plan should contain.** Derived from the diff between the branches and
from what production is missing today. Treat the counts as shapes to check, not
as a number to match, and read every destroy line.

| Group | Expect | Note |
| --- | --- | --- |
| KMS signing key, alias, key policy | 3 create | `aws kms list-aliases` currently matches nothing containing `identity` |
| Identity tables | 10 create | `credentials`, `refresh-tokens`, `login-attempts`, `identity-tokens`, `totp-factors`, `recovery-codes`, `passkeys`, `webauthn-challenges`, `oauth-states`, `oauth-links`. All carry `deletion_protection = true` because `var.environment == "production"` |
| IAM role policies on the identity role | 2 to 3 create | `identity-signing`, `identity-tables`, plus `identity-ses` from `ses.tf` |
| SES | 2 create plus 3 DKIM CNAMEs | `aws_sesv2_email_identity.primary`, `aws_sesv2_configuration_set.identity`, `aws_route53_record.ses_dkim[0..2]` |
| `aws_route53_record.ses_dmarc` | **0 changes** | If this shows a create or update, blocker 1 is not fixed. **Hard stop.** |
| Gateway routes | many create | The M2 to M6 route keys added by `apigateway.tf` |
| Gateway authorizer | **0** | Mode is `off`. Any `aws_apigatewayv2_authorizer` in this plan is wrong. **Hard stop.** |
| Identity Lambda environment | 1 update | The `IDENTITY_*` block lands on `webbpulse-production-identity` |
| `webbpulse-production/app` secret version | 1 update | The two `OAUTH_*_CLIENT_SECRET` keys |
| Destroys | **expect none** | Verify. A destroy of a data table here is a stop. |

Because production has none of the identity stack, the `moved` blocks in
`identity.tf` are no-ops there: there is nothing to move from, so every one of
those resources is a plain create. That is expected and is not the same plan
staging saw.

**Gate:** the plan contains no destroy of any DynamoDB table, no authorizer, and
no change to `ses_dmarc`. Otherwise do not apply.

Apply, and wait for `applied`.

### Step 4. Verify the first apply landed

```bash
export AWS_PROFILE=Portfolio-Production/AdministratorAccess
aws dynamodb list-tables --region us-west-2 \
  | jq -r '.TableNames[] | select(test("credential|refresh|login-attempt|identity-token|totp|recovery|passkey|webauthn|oauth"))'
aws kms list-aliases --region us-west-2 \
  --query "Aliases[?contains(AliasName,'identity')].AliasName"
aws sesv2 get-email-identity --region us-west-2 \
  --email-identity webbpulse.com \
  --query '{Verified:VerifiedForSendingStatus,DkimStatus:DkimAttributes.Status}'
```

Expect ten tables, one alias, and DKIM moving to `SUCCESS`. DKIM verification is
DNS-propagation bound and can take minutes to an hour; it does not block the
next step, because nothing in the promotion sends mail.

Confirm the DMARC record is untouched:

```bash
dig +short TXT _dmarc.webbpulse.com @1.1.1.1
```

Expect `"v=DMARC1; p=none; rua=mailto:tyler@webbpulse.com"`. **If it changed,
restore it in the management account, 488386929690, immediately.**

### Step 5. Deploy the backend so the identity function serves discovery

The Terraform apply set the identity function's environment but did not change
its code. `deploy-backend.yml` runs on pushes to `main`, so the merge in step 2
should already have built and deployed the four domain images. Confirm rather
than assume:

```bash
gh run list --branch main --workflow deploy-backend.yml --limit 3
```

The chain is `resolve-env`, `build-images`, `image-map`, `deploy-images`,
`smoke-domains`, `verify-route-cuts`. `resolve-env` binds the `production`
GitHub Environment from `github.ref_name == 'main'`.

If the run did not fire, or predates the apply, dispatch a fresh one. Do not
re-run an old run: a re-run reuses the old reusable-workflow ref.

```bash
gh workflow run deploy-backend.yml --ref main
```

Then confirm the function was actually updated:

```bash
AWS_PROFILE=Portfolio-Production/AdministratorAccess \
  aws lambda get-function-configuration --region us-west-2 \
    --function-name webbpulse-production-identity \
    --query '{Modified:LastModified,Env:keys(Environment.Variables)}'
```

`Env` must now list the `IDENTITY_*` keys, and `Modified` must be after the
apply.

### Step 6. Gate: discovery and JWKS must serve before mode native

This is the gate the two-apply constraint exists for.

```bash
curl -s https://api.webbpulse.com/api/auth/.well-known/openid-configuration | jq .
curl -s -o /dev/null -w "%{http_code}\n" \
  https://api.webbpulse.com/api/auth/.well-known/jwks.json
```

Required:

- Both return `200`. Today both return `404`.
- `issuer` is exactly `https://api.webbpulse.com/api/auth`, with the path. The
  issuer carries its path, and a bare host was proven wrong during the M0 spike.
- `jwks_uri` is exactly `https://api.webbpulse.com/api/auth/.well-known/jwks.json`.
- The JWKS body contains at least one RSA key.

For comparison, staging serves
`{"issuer": "https://api.staging.webbpulse.com/api/auth", "jwks_uri": "https://api.staging.webbpulse.com/api/auth/.well-known/jwks.json"}`.

**No-go if any of these fail.** Setting `identity_jwt_mode = native` against a
`404` fails `CreateAuthorizer` and fails the apply.

### Step 7. Migrate the administrator credential

Dry run first. The script is dry run by default and `--apply` is what writes.

```bash
cd backend
AWS_PROFILE=Portfolio-Production/AdministratorAccess AWS_REGION=us-west-2 \
  python scripts/migrate_credentials_to_identity.py --prefix webbpulse-production
```

`--prefix` selects the environment for **both** tables: it is written back into
`DYNAMODB_TABLE_PREFIX` inside `parse_args`, because the legacy users repository
reads that setting rather than the flag and would otherwise hit
`webbpulse-development-users`.

Expect one user, classified as a copy, with no conflicts. The hash copies
verbatim: both sides are `webbpulse.security.hash_password`, bcrypt cost 12, so
the administrator keeps their existing password and no reset is involved.

**Gate:** the dry run reports zero conflicts and zero unsupported hashes. A row
whose hash is not a bcrypt modular crypt string is skipped and reported, and that
is a stop rather than a warning.

Then write:

```bash
AWS_PROFILE=Portfolio-Production/AdministratorAccess AWS_REGION=us-west-2 \
  python scripts/migrate_credentials_to_identity.py --prefix webbpulse-production --apply
```

The script is idempotent. A rerun leaves an identical credential untouched,
`created_at` included. A differing credential is a conflict and a non-zero exit
rather than an overwrite, and `--replace` is the deliberate override. Do not pass
`--replace` on a first run.

**Do not clear the legacy column yet.** That is step 11, after a real identity
sign-in.

### Step 8. Second apply, mode native

Add the variable to the production workspace. This is an owner action in the HCP
UI, or:

```bash
T=$(jq -r '.credentials["app.terraform.io"].token' ~/.terraform.d/credentials.tfrc.json)
curl -s -X POST -H "Authorization: Bearer $T" \
  -H "Content-Type: application/vnd.api+json" \
  -d '{"data":{"type":"vars","attributes":{"key":"identity_jwt_mode","value":"native","category":"terraform","sensitive":false,"description":"Native API Gateway JWT authorizer. Requires the identity function to be serving discovery."}}}' \
  https://app.terraform.io/api/v2/workspaces/ws-JpNLUhFzVCzMDgAN/vars
```

The validation in `variables.tf` refuses `native` when `environment` is
`staging`, so this is only ever valid here.

Queue a run. **What this plan should contain:**

| Group | Expect |
| --- | --- |
| `aws_apigatewayv2_authorizer` | 1 create, type `JWT` |
| Marked routes | replace, not update. Seven route keys carry `require_identity_jwt`, split five and two across the M4 and M6 groups, so expect roughly seven replacements: verify the exact count against `module.api.identity_jwt_route_keys` in the plan output |
| `.well-known` routes | **unchanged**. They must stay anonymous, since the authorizer fetches them |
| `/login/mfa` | **unchanged and unprotected**. Its caller holds an MFA ticket whose `aud` is `<issuer>/mfa`, not the API audience, so an authorizer configured with the API audience would reject a valid ticket |
| Everything else | no change |

Route replacement is briefly disruptive on those routes. It is seconds, and the
routes being replaced are the authenticated admin routes rather than the public
site.

**Gate:** the plan replaces only routes that carry `require_identity_jwt`, and
touches neither `.well-known` route. Then apply.

If the apply fails inside `CreateAuthorizer` with a message about fetching the
discovery document, step 6's gate was passed prematurely. Set
`identity_jwt_mode` back to `off`, apply to clean up, and return to step 5.

### Step 9. Verify the production identity path end to end

```bash
API=https://api.webbpulse.com

# Anonymous, must still be 200. These are outside the authorizer.
curl -s -o /dev/null -w "discovery %{http_code}\n" $API/api/auth/.well-known/openid-configuration
curl -s -o /dev/null -w "jwks      %{http_code}\n" $API/api/auth/.well-known/jwks.json

# A protected route with no token, must be 401 and must come from the gateway.
curl -s -o /dev/null -w "no token  %{http_code}\n" $API/api/auth/sessions

# The public site, unchanged throughout.
curl -s -o /dev/null -w "health    %{http_code}\n" $API/health
curl -s -o /dev/null -w "projects  %{http_code}\n" $API/api/v1/projects
curl -s -o /dev/null -w "content   %{http_code}\n" $API/api/v1/site-content
```

Expect `200, 200, 401, 200, 200, 200`. The last three are the regression check:
they are `200` today and must stay `200`.

Then a real sign-in, with the administrator's own password:

```bash
curl -s -X POST $API/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<admin>","password":"<password>"}' \
  | jq '{has_access: (.access_token != null), token_type}'
```

Do not paste the password into a shared transcript. Then call a protected route
with the returned access token and expect `200`.

Confirm the OAuth providers are advertised, which is the behavioural check that
the two secret keys landed in the `app` blob:

```bash
curl -s $API/api/auth/oauth/providers | jq .
```

Expect both `google` and `github`. An empty list means a client id or secret is
missing or misspelled, since a provider is counted only when it carries a client
id and the secret lookup is a plain dict get with no error on a miss. **Never
call `get-secret-value` to check this.**

Passkey routes will not be present, because `passkeys_enabled` derives to
`false` in production. That is expected.

**Gate:** password sign-in works through `/api/auth/login`, a protected route
accepts the token, and the three public routes are unchanged. Otherwise roll back
before touching the frontend.

## Addendum 2026-09-11

**This section was added after the runbook above was written, and it inserts a
step between step 9 and step 10.** It is marked off rather than folded into the
numbering because the steps either side kept their numbers and anyone following
a printed copy needs to see that something landed in the middle.

### Why it exists

The runbook above promotes the identity stack and then flips the frontend. That
sequence is correct for `/api/auth`, which was built against identity from the
start. It is not sufficient for the `/api/v1` admin routes: those verified only
the legacy HS256 token, so an administrator signed in through the identity path
held a credential they could not read. Step 9 would pass, step 10 would flip the
frontend, and the admin panel would sign in and then answer 401 on every write.

The backend now accepts either credential, and the gateway has to be told which
route keys carry the claims it falls back to. That is what this step does. See
"Admin routes in identity mode" in `docs/identity-cutover.md` for the mechanism.

### Step 9a. Apply the admin route keys, then enforce them

Two applies, in this order. Both are on the production workspace.

**First, merge this change to `main` and apply with `domain_jwt_enforced`
absent.** The variable defaults to false, so do not set it yet.

Expected plan: **adds only.** 24 `aws_apigatewayv2_route` additions, one per
flagged admin route key, and nothing else. No changes and no destroys. If the
plan shows a change or a destroy, stop: the keys are meant to route exactly where
the existing greedy keys already routed, and anything else means a key is
colliding with one that exists.

This apply changes no behaviour. The new keys are more specific than the greedy
ones so they win route selection, but they point at the same integration, and
without the flag the gateway asks the caller for nothing new. It is safe to land
while the frontend is still in bearer mode, and safe to leave sitting here.

**Then set `domain_jwt_enforced = true` on the production workspace and apply
again.**

```bash
# Production workspace: ws-JpNLUhFzVCzMDgAN
```

Expected plan depends on the mode production is in by this point:

| `identity_jwt_mode` | Expected plan | What moved |
|---|---|---|
| `gate` | `0 add 1 change 0 destroy` | the access gate authorizer's Lambda environment only |
| `native` | 24 route changes | each flagged key moves onto the JWT authorizer |

Production reaches step 9 in `native` mode, per step 8, so expect the second
shape there. Count the changed routes and confirm it is 24, not more: a larger
number means a key that should have stayed anonymous is being enforced, and the
public site is about to start asking visitors for a token.

**Gate:** the second apply has finished and the plan matched one of the two
shapes above. Then, and only then, go to step 10.

### The window between the flag and the frontend

**Between this step's second apply and step 10's frontend deploy, admin writes
from the browser fail.** The gateway now requires an identity access token on
those 24 routes, and the deployed bundle is still in bearer mode, so it sends the
legacy token and the gateway refuses the request before the application sees it.

This is a real window and it is worth stating plainly rather than discovering it:

- It lasts from the second apply to the end of the frontend deploy.
- It affects admin writes only. Every public read is unflagged and unaffected, so
  the site stays up for visitors throughout.
- The fix is to finish step 10, not to roll anything back.

Keep the window short by having step 10 ready to run before starting the second
apply. If something goes wrong mid-window, rolling back the flag is faster than
rolling forward.

### Rollback for this step

Set `domain_jwt_enforced` back to false and apply. That is the whole of it for
the gateway half: the route keys stay, enforcement stops, and admin writes work
again against the legacy token.

If the frontend has already been flipped, roll that back too by removing the
`AUTH_MODE` variable and redeploying:

```bash
gh variable delete AUTH_MODE --env production --repo WebbPulse/WebbPulse-Portfolio
gh workflow run deploy-frontend.yml --ref main
```

The backend needs no rollback either way. It accepts both credentials, so it is
correct in every combination of the two flags.

**This rollback stops working once step 11 has run.** Clearing the legacy column
removes the password the bearer path verifies against, so after that point the
identity path is the only way in and the rollback is fix-forward. That is the
same constraint the "Rollback" section below describes for step 11.

### Step 10. Flip the frontend to identity mode

The production GitHub Environment has no `AUTH_MODE` variable today, so the
frontend builds in `bearer` mode. `VITE_AUTH_MODE` defaults to `bearer` when
absent.

```bash
gh variable set AUTH_MODE --env production --body identity \
  --repo WebbPulse/WebbPulse-Portfolio
gh workflow run deploy-frontend.yml --ref main
```

`CODEARTIFACT_DOMAIN_OWNER` is set at repository level (`432410731887`), so it
resolves for the production environment too, and the production deploy role
already carries `codeartifact:GetAuthorizationToken` and the package read
actions. No new GitHub variable is needed.

Then sign in at `https://www.webbpulse.com` in a browser, through the admin
panel, and confirm the session survives a reload. The refresh cookie is
`SameSite=Lax`.

**Gate:** a browser sign-in through the identity path succeeds. This gate is what
step 11 is waiting on.

### Step 11. Clear the legacy column

Only after step 10's browser sign-in. This is the step that makes the identity
store the only place the administrator's password exists.

```bash
cd backend
AWS_PROFILE=Portfolio-Production/AdministratorAccess AWS_REGION=us-west-2 \
  python scripts/clear_legacy_credentials.py --prefix webbpulse-production
```

Read the classification. `cleared` and `already_clear` are fine; `mismatch` and
`missing_credential` are refusals that exit non-zero and want a person, because
both mean removing the column would take away a way in without having confirmed
another one exists.

Then:

```bash
AWS_PROFILE=Portfolio-Production/AdministratorAccess AWS_REGION=us-west-2 \
  python scripts/clear_legacy_credentials.py --prefix webbpulse-production --apply
```

The attribute is removed rather than blanked. The admin seeder is identity aware
and owns the user row and the identity credential but never the legacy column,
so a cleared column stays cleared instead of being rewritten on the next cold
start.

Sign in once more after clearing, to confirm the identity path is genuinely
standalone.

### Step 12. Close out

- [ ] Delete `~/prod-users-preflight.json`.
- [ ] Confirm `dig +short TXT _dmarc.webbpulse.com` is still `p=none` with its `rua`.
- [ ] Confirm the CloudWatch alarms are quiet.
- [ ] Note whether SES DKIM reached `SUCCESS`, and that sending is
      sandbox-limited until an owner-approved support case says otherwise.
- [ ] Decide separately on `passkeys_enabled` and on leaving the SES sandbox.

## Rollback

Rollback gets narrower at every step, and the honest summary is that **it is
cheap before step 7 and not cheap after step 11.**

### What reverting `main` does undo

Reverting `main` to the sha recorded in step 1 and pushing rebuilds and
redeploys the previous backend image and the previous frontend bundle. The
frontend returns to `bearer` mode once `AUTH_MODE` is also removed from the
production environment, and the legacy `POST /api/v1/admin/login` serves again.
That covers the application layer.

```bash
gh variable delete AUTH_MODE --env production --repo WebbPulse/WebbPulse-Portfolio
git revert --no-commit <promotion-merge-sha>
```

### What reverting `main` does not undo

- **The gateway authorizer.** It is Terraform state, not code deployment.
  Removing it means setting `identity_jwt_mode` back to `off` and applying.
  Until that apply runs, the protected routes keep demanding a JWT, and a
  reverted frontend that stopped sending one is locked out of the admin panel.
  **Revert the variable and apply before or alongside the code revert, not
  after.**
- **The identity tables and the KMS key.** A revert of the code plans them for
  destroy, and all ten tables carry `deletion_protection = true` in production
  because of `var.environment == "production"`. So the destroy fails rather than
  losing data, which is the safe failure, but it does mean a clean revert needs
  the resources removed from state or the protection lifted deliberately. Prefer
  leaving them: an unused table costs nothing and holds the migrated credential.
- **The SES identity and the DKIM CNAMEs.** Destroying them unverifies the
  sending domain, and re-verification is another DNS round trip. Prefer leaving
  them.
- **The cleared `hashed_password` column, step 11.** This is the one-way door.
  Once cleared, the legacy login has no hash to verify against, so reverting the
  code restores a login path that cannot authenticate anybody. Recovery is either
  restoring the column from the step 1 snapshot or re-seeding the administrator
  from `admin_password`. This is why step 11 sits behind a real browser sign-in
  and why the snapshot is taken in step 1.
- **Anything written through the identity path after the cutover.** A password
  changed through `POST /api/auth/password` exists only in the `credentials`
  table, and a revert to the legacy column resurrects the old password.

### The practical rollback, by step reached

| Reached | Rollback |
| --- | --- |
| Through step 6 | Set `identity_jwt_mode` off if it was set, revert `main`. The identity stack sits unused and harmless. |
| Through step 9 | Set `identity_jwt_mode` to `off`, apply, then revert `main`. Frontend was never flipped. |
| Through step 10 | As above, plus delete the `AUTH_MODE` variable and redeploy the frontend. The legacy column is still populated, so bearer login works immediately. |
| After step 11 | Restore `hashed_password` from the step 1 snapshot before reverting, or accept that the only way in is the identity path and fix forward instead. Fixing forward is usually right here. |

## Recommended sequence, short form

1. Fix the `ses_dmarc` gate on `staging` and confirm a production plan shows no
   change to `_dmarc.webbpulse.com`.
2. Merge `staging` into `main` with `identity_jwt_mode` absent, and apply: the
   identity stack, ten tables, KMS key and SES are created, no authorizer.
3. Confirm `deploy-backend.yml` ran on `main` and that
   `https://api.webbpulse.com/api/auth/.well-known/openid-configuration` returns
   `200` with the path-carrying issuer.
4. Dry run and then apply `migrate_credentials_to_identity.py --prefix webbpulse-production`,
   set `identity_jwt_mode = native`, and apply the second run.
5. Verify sign-in, set `AUTH_MODE=identity` on the production environment,
   redeploy the frontend, confirm a browser sign-in, and only then run
   `clear_legacy_credentials.py --apply`.

## Executed 2026-09-11, steps 9a and 10

What actually ran in production for the admin route enforcement and the frontend
flip, recorded against the addendum above. Steps 0 through 9 are recorded
separately; this section starts from the point where the identity stack was
already live, the native JWT authorizer already carried the 15 `/api/auth`
routes, and the administrator had signed in successfully through
`POST https://api.webbpulse.com/api/auth/login` at 06:39Z.

Step 11 was deliberately not run. The legacy `hashed_password` column is still
populated, so the rollback described in the addendum still works.

### The release merge

PR 193, `staging` into `main`, "Release: per-domain CI matrix and the repository
level gate". Merged with a merge commit rather than a squash, which is what this
repository does for a staging to main promotion.

| Thing | Value |
| --- | --- |
| Merge commit | `b9db85c02cbcdf134d6de5e4c469dd2b24f7b00c` |
| Required check | `all-checks-passed`, green before the merge |
| `Deploy Backend` run | `34573028977`, success at 07:11:51Z |

The backend run built all four domain images (`content`, `resume`, `identity`,
`public`), deployed them, and passed both `verify-route-cuts` and
`smoke-domains`. The route cut verification passing before the first apply is
what makes the next step's plan trustworthy: the route keys Terraform is about
to write are the ones the built applications actually serve.

### First apply, flag absent

Run `run-kKkAoHyXtviUFYzk` on `ws-JpNLUhFzVCzMDgAN`, the VCS run for the merge
commit. `domain_jwt_enforced` did not exist on the workspace, so it took its
`false` default.

**Plan: 24 to add, 0 to change, 0 to destroy.** Exactly the addendum's expected
shape. Every one of the 24 was an `aws_apigatewayv2_route` create under
`module.api.aws_apigatewayv2_route.this`, nine on `content` and fifteen on
`resume`, matching `local.domain_identity_jwt_route_paths` key for key. Nothing
else appeared in the plan: no `random_password`, no DynamoDB table, no KMS key,
no Route 53 record, and no change to the JWT authorizer created in step 8.

The platform modules float to 2.11.0 rode along in this merge and was a no-op
here, as expected: production does not use the staging access gate module, which
is the only thing 2.11 changed.

Applied at 07:13:44Z. Verified against the live gateway with
`aws apigatewayv2 get-routes --api-id v41a6bqcl1`:

- 77 routes total.
- All 24 expected keys present, none missing.
- All 24 carrying `AuthorizationType: NONE` and no `AuthorizerId`, which is the
  inert state the addendum describes.
- The only routes on the API carrying an authorizer were the 15 `/api/auth`
  routes from step 8, on authorizer `1ii09i`, unchanged.

Behaviour was unchanged by this apply, confirmed by probe:
`GET /api/v1/posts`, `GET /api/v1/site-content` and `GET /api/v1/projects` all
`200`, and `POST /api/v1/posts/admin` with no token still answered `403` from
the application rather than `401` from the gateway.

### Second apply, flag on

`domain_jwt_enforced` was created on the workspace as a `terraform` category
variable with `hcl = true` and the value `true`, because the variable is
`type = bool`. The existing `identity_jwt_mode` was created the same way except
for `hcl`, since its value is a string.

Run `run-xUPq2RpVre9Mu9Kh`, message "Step 9a: enforce identity JWT on admin
routes".

**Plan: 24 to add, 0 to change, 24 to destroy.**

This is worth stating carefully, because the addendum's table calls it "24 route
changes" and a reader expecting `0 add 24 change 0 destroy` will see this and
stop. The replacement shape is the correct one in `native` mode, and
`variable "domain_jwt_enforced"` in `terraform/variables.tf` says so directly:
"In production, where `identity_jwt_mode` is `native`, a marked route moves onto
the module's JWT authorizer resource, so the 24 keys are replaced rather than
updated in place."

What the plan actually contained, checked rather than assumed:

- 24 deletes, all `module.api.aws_apigatewayv2_route.this[<key>]`.
- 24 creates, all `module.api.aws_apigatewayv2_route.identity_jwt[<key>]`.
- The two key sets are **identical**, compared as sets in both directions. No
  key is deleted without being recreated and none appears only on the create
  side.
- `aws_apigatewayv2_route` is the only resource type in the plan. No other
  resource of any type changed.
- Each created route carries `authorization_type = "JWT"` and
  `authorizer_id = "1ii09i"`, which is the authorizer step 8 created, and the
  same `target` integration the deleted route pointed at.

So the count that matters, the number of route keys that moved onto the
authorizer, is 24 and not more. Neither `.well-known` route and no public read
appears anywhere in the plan.

Applied at 07:17:41Z, run finished 07:17:47Z.

### Verification after enforcement

Probes against `https://api.webbpulse.com`, immediately after the apply:

| Probe | Result |
| --- | --- |
| `GET /api/v1/posts` | `200` |
| `GET /api/v1/site-content` | `200` |
| `GET /api/v1/projects` | `200` |
| `GET /health` | `200` |
| `POST /api/v1/posts/admin`, no token | `401`, `www-authenticate: Bearer`, body `{"message":"Unauthorized"}` |
| `POST /api/v1/posts/admin`, `Authorization: Bearer not-a-token` | `401`, `www-authenticate: Bearer scope="" error="invalid_token" error_description="token contains an invalid number of segments"` |

Both 401s carry an `apigw-requestid` and no application error envelope, which is
how you tell the gateway refused the request before the function saw it. The
second one is the more informative of the two: the authorizer parsed the header,
failed to read a JWT out of it, and said so. That is the enforcement working.

### Step 10, the frontend flip

`AUTH_MODE=identity` set on the `production` GitHub Environment at 07:18:03Z.
The mechanism is build time: `deploy-frontend.yml` passes
`VITE_AUTH_MODE: ${{ vars.AUTH_MODE }}` into `npm run build`, and
`frontend/src/services/api.ts` reads it once at startup through `ConfigReader`,
falling back to `bearer` when absent.

`Deploy Frontend` dispatched on `main`, run `34573737408`, success at 07:20:21Z.

Confirmed in the shipped artefact rather than in the workflow log. The bundle
name changed from `index-BegbBg5K.js` to `index-BLzXYflL.js`, and the embedded
marker changed with it:

| When | Marker in the bundle |
| --- | --- |
| Before | `VITE_AUTH_MODE:""` |
| After | `VITE_AUTH_MODE:"identity"` |

An empty string is what the bearer fallback looks like after Vite's build time
substitution, so those two strings are the whole of the flip as the browser sees
it. `https://webbpulse.com` returned `200` and `GET /api/v1/site-content`
returned `200` afterwards.

### The window

The addendum warns that admin writes from the browser fail between the flag
apply and the frontend deploy. They did, and the window was:

| Boundary | Time |
| --- | --- |
| Flag apply finished | 07:17:47Z |
| Frontend deploy finished | 07:20:21Z |
| **Duration** | **2 minutes 34 seconds** |

Public reads were unaffected throughout, which the probes above confirm at both
ends. Keeping the window this short came from having the `gh variable set` and
the workflow dispatch ready to run before the second apply was queued, which is
what the addendum recommends.

### What the runbook got right and what it did not

Right: the two apply split, the 24 count, the inert first apply, the direction of
the window, and the advice to have step 10 staged before starting the flag apply.

Not quite right: the addendum's expected plan table for `native` mode says "24
route changes", which reads as 24 in place updates. It is 24 replacements, so
`24 add 0 change 24 destroy`. The variable's own documentation has this correct
and the table should be read against it. Anyone following this step should
compare the deleted and created key sets rather than the headline counts, since
the headline counts alone cannot distinguish a clean one for one move from a key
being dropped and a different one added.

### Left open

- **Step 11 has not run.** `clear_legacy_credentials.py --apply` is deliberately
  not executed, so the legacy `hashed_password` column is intact and the
  addendum's rollback still works in full. It is waiting on the owner making one
  admin write through the identity path in a browser, which is the gate step 11
  has always had.
- SES DKIM remains `PENDING` and sending is still sandbox limited. Neither
  blocks the admin path.
