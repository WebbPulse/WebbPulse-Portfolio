# Identity runbook

The identity cutover is complete in both environments except for the two steps
below. Identity is the only auth mode the frontend can build: the mode switch
was removed, so there is nothing left to select. Production runs with gateway
JWT enforcement on the 24 admin route keys. Staging runs in `gate` mode with the
legacy column already cleared.

This file is the current state, the two remaining steps, and the operational
reference for the optional identity features. The migration narrative is in
`docs/migration/RETROSPECTIVE.md`.

## Where each environment stands

| | Staging | Production |
| --- | --- | --- |
| Frontend auth mode | identity, the only mode | identity, the only mode |
| `identity_jwt_mode` | `gate` | `native` |
| `domain_jwt_enforced` | n/a in gate mode | `true` on the workspace |
| Legacy `hashed_password` column | cleared | **still populated** |
| Passkeys | derived on | derived off |
| Passwordless | derived on | off, owner decision |
| OAuth providers | client ids unset | client ids unset |

`var.domain_jwt_enforced` defaults to `false` in `terraform/variables.tf` and is
overridden to `true` as an HCP workspace variable on `WebbPulse-Portfolio`
(`terraform` category, `hcl = true`). The repository default is not evidence
that enforcement is off. Read the workspace through the HCP API to confirm.

**Rollback from either environment is fix-forward.** There is no build time
switch back: the bearer branch, its token store and `authMode.ts` are deleted,
so a rollback means reverting the frontend to a commit that still carried them.
Staging has also run the column clear, so a bearer bundle there would produce a
sign-in page nobody can get past. Production still has its legacy column until
Step 11 runs.

### Resolved: the build time auth mode switch is gone

`VITE_AUTH_MODE` forwarding was added in `ff29cd2` and dropped in `ce34362`, the
commit that moved the deploy onto the org `spa-deploy.yml`. Because
`authMode.ts` fell back to `bearer` when the variable was absent, every frontend
build after `ce34362` shipped a bearer bundle against gateway routes that
enforce identity JWTs. That included the production deploy of `ec1c3e5f` on
2026-09-12, so the defect reached production rather than merely threatening it.

Forwarding the variable again would have restored the same fragile coupling: a
bundle whose auth mechanism depended on an environment variable that nothing
verified. Both environments had already been on `AUTH_MODE=identity` since
2026-09-11, so the bearer branch was dead configuration.

The switch was therefore removed rather than repaired. `authMode.ts` and
`bearerTokenStore.ts` are deleted, `ApiService` always constructs an
`AuthClient`, and `getAuthClient` and `getIdentityClient` no longer return null.
Identity is structural, not configured, so no GitHub Environment variable
selects it and none can turn it off. The `AUTH_MODE` variables still present on
both environments are inert and can be deleted at any time.

Two guards keep it that way. `frontend/src/services/api.test.ts` asserts in
`built auth mode` that sign-in goes to `/api/auth/login`, that nothing posts to
`/admin/login` and that no access token reaches `localStorage`. The
`resolve-env` job in `deploy-frontend.yml` fails the deploy if `frontend/src`
reintroduces `VITE_AUTH_MODE` or the legacy login route.

## Step 11. Clear the legacy column in production

**Pending.** It is gated on the owner making one admin write through the
identity path in a browser. This is the step that makes the identity store the
only place the administrator's password exists, and it is a one-way door.

```bash
cd backend
AWS_PROFILE=Portfolio-Production/AdministratorAccess AWS_REGION=us-west-2 \
  python scripts/clear_legacy_credentials.py --prefix webbpulse-production
```

Read the classification. `cleared` and `already_clear` are fine; `mismatch` and
`missing_credential` are refusals that exit non-zero and want a person, because
both mean removing the column would take away a way in without having confirmed
another one exists. A `mismatch` is usually a password changed through
`POST /api/auth/password` after the migration ran, in which case the identity
store is correct and newer than the column, but the script will not make that
judgement on its own. No hash is printed, in the summary, a detail line or an
error.

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

**Rollback changes shape after this step.** Up to here, rolling back is a
variable and a redeploy. Once the column is removed the legacy login verifies
every password against a dummy hash, so it refuses everybody rather than
erroring. Rolling back from there means first re-migrating in the other
direction, writing each user's secret from the identity `credentials` table back
onto the `users` row, and there is deliberately no script for that. The identity
store is the system of record from this step onward.

## Step 12. Close out

**Pending**, after Step 11.

- [ ] Delete `~/prod-users-preflight.json`.
- [ ] Confirm `dig +short TXT _dmarc.webbpulse.com` is still `p=none` with its `rua`.
- [ ] Confirm the CloudWatch alarms are quiet.
- [ ] Note whether SES DKIM reached `SUCCESS`, and that sending is
      sandbox-limited until an owner-approved support case says otherwise.
- [ ] Decide separately on `passkeys_enabled` and on leaving the SES sandbox.

## Later, in a separate PR: remove the legacy routes

The frontend half is done: `BearerTokenStore` and `authMode.ts` are deleted and
nothing in the bundle calls `POST /api/v1/admin/login`. What remains is the
backend half, `POST /api/v1/admin/login` with `app/domains/identity/router.py`
and the `hashed_password` column, which go together once production has run on
identity long enough to be confident. Until that PR lands the legacy routes stay
mounted and unused, which is what still makes a frontend revert a working
rollback. Once they are removed, rollback stops working entirely.

## Admin routes in identity mode

The `/api/auth` routes were built against the identity stack. The `/api/v1`
admin routes predate it and originally verified only the legacy HS256 token, so
an identity access token (RS256, KMS-signed, numeric `sub`) could not be read by
them.

**The backend accepts either credential.** `get_current_user` tries the legacy
HS256 token first and falls back to the claims an authorizer put on the request.
The fallback resolves the numeric `sub` to a user row and applies the same
`is_admin` and `is_active` checks, so a disabled account is refused whatever it
presents.

**The application does not verify the signature, and has no KMS access.** The
gateway is the verifier: API Gateway's own JWT authorizer in `native` mode, the
staging access gate's Lambda in `gate` mode. Claims arrive in the
`x-amzn-request-context` header, which the Lambda Web Adapter writes from the
invoke event. API Gateway does not forward an inbound header of that name and
the adapter overwrites it regardless, so a caller cannot fabricate one.

**A route only gets claims if its route key is flagged.** An unflagged route
carries no claims, the fallback finds nothing, and the 401 comes back.
`backend/tests/entrypoints/test_gateway_routes.py` derives the set of routes
requiring an administrator from the FastAPI app and asserts it equals the
flagged keys in `apigateway.tf`, in both directions, so neither half can drift.

### The two claim shapes

| Mode | Where the claims land | Shape |
|---|---|---|
| `native` | `requestContext.authorizer.jwt.claims` | flat string map, `exp` included |
| `gate` | `requestContext.authorizer.lambda["jwt.claims"]` | one JSON string, values stringified |

A Lambda authorizer's context always lands under `lambda` and API Gateway
refuses a nested object there, so the gate uses a single string key and
stringifies the values so `exp` reads the same way in both environments.
`app/core/identity_claims.py` reads both and returns identical Python values.

### The 24 flagged routes

| Domain | Count | Routes |
|---|---|---|
| `content` | 9 | the `/api/v1/posts/admin` collection and item routes, `POST /api/v1/posts/admin/{post_id}/publish`, the three `/api/v1/posts/categories` writes, and `PUT /api/v1/site-content` |
| `resume` | 15 | `POST`, `PUT /{item_id}` and `DELETE /{item_id}` across `certifications`, `education`, `experience`, `projects` and `skills` |

The other 16 `/api/v1` routes stay anonymous: 15 public reads plus
`POST /api/v1/admin/login`, which is how a caller gets a token and must stay
reachable without one.

**No anonymous guard keys were needed.** API Gateway prefers a static segment
over a variable at the same depth and a concrete method over `ANY`, so a new key
can shadow a public route. Here it cannot: every flagged `{param}` key is a
`PUT`, `POST` or `DELETE`, every public route at the same depth is a `GET`, and
a route key matches only its own method.

### Changing enforcement

Enforcement is two applies, never one. Apply with `domain_jwt_enforced` absent
to land the route keys inert, then set it to `true` and apply again. In `native`
mode the second plan is `24 add, 0 change, 24 destroy`, a replacement rather
than an in-place update: compare the deleted and created key sets rather than
the headline counts. In `gate` mode it is `0 add, 1 change, 0 destroy`, the
access gate authorizer's Lambda environment only.

Between the enforcing apply and the frontend deploy, admin writes from the
browser fail. Public reads are unaffected. The fix is to finish the frontend
deploy, not to roll back, and the window is kept short by staging the
`gh variable set` and the workflow dispatch before queueing the apply.

## Two factor authentication

Six routes under `/api/auth` and two DynamoDB tables, `totp-factors` and
`recovery-codes`. Enrolment is per account and opt in; a login for a user with
no active factor answers exactly as it did before. No policy requires it.

Enrolment is a step-up operation. `POST /api/auth/step-up` raises a plain
session to one allowed to change a factor. `POST /api/auth/totp/enrol` returns a
new seed as an `otpauth://` URI and its QR payload, exactly once, and nothing
reads it back. `POST /api/auth/totp/activate` takes the six digit code; the
factor is inactive until this succeeds, so a mis-scanned seed cannot lock anyone
out. `POST /api/auth/totp/disable` requires `{"code": "..."}` in the body as
well as the bearer token.

**Recovery codes are shown once**, in the activation response. Only a hash of
each is stored, so the server cannot redisplay them.
`POST /api/auth/recovery-codes` issues a fresh set and invalidates every
previous code in the same write; it requires a current TOTP code or an unused
recovery code in the body, not a stepped-up session, because accepting a
recently stepped-up access token would reintroduce the bearer-token-only path
the code requirement closes. Verification happens before the old set is deleted.
Each code is single use and none expire. Keep them in 1Password alongside the
account, not in the authenticator app that holds the factor.

**The seed is never stored in plaintext.** `MfaService` seals it with a KMS
envelope under the identity module's TOTP key, encryption context
`purpose=totp` plus the user id, so a sealed seed lifted from one row cannot be
unsealed as another user's. The key ARN arrives as `IDENTITY_DATA_KEY_ARN`. A
deployment missing it still serves all six routes and fails at the first
enrolment naming the variable.

## OAuth providers

Five routes under `/api/auth/oauth` and the `oauth-states` and `oauth-links`
tables. **None of the five routes mount until a provider client id is
configured.** Both client id variables are empty in both environments, so the
OpenAPI document contains no `/api/auth/oauth` path at all, asserted by
`backend/tests/test_identity_m6.py`.

Client ids go to HCP as workspace variables (`oauth_google_client_id`,
`oauth_github_client_id`); the secrets go into the `webbpulse-<env>/app` JSON
secret under `oauth_google_client_secret` and `oauth_github_client_secret`. Set
the secret first, then the variable, then apply. The redirect URI is derived
from `local.identity_issuer`:

| Environment | Redirect URI |
| --- | --- |
| staging | `https://api.staging.webbpulse.com/api/auth/oauth/callback` |
| production | `https://api.webbpulse.com/api/auth/oauth/callback` |

## Passkeys

Seven routes under `/api/auth`, plus `GET /api/auth/passkeys/availability`,
which mounts in every deployment regardless of either flag and answers
`{"enabled": <bool>, "passwordless": <bool>}` with
`Cache-Control: public, max-age=300`. The frontend reads it to decide what to
draw, so a flipped variable changes the affordance within five minutes.

**Both flags derive from `var.environment`, not from HCP.** Each is a nullable
variable in `terraform/identity.tf` with a null default, and null means the
environment's answer: true in staging, false in production. The package's own
default for both is true, which is the opposite of what production ships, so
the locals always render an explicit bool. Setting either variable on a
workspace overrides the derived answer, which is what keeps rollback a one
variable change with no code deploy.

| Variable | Resolves to | What true means |
|---|---|---|
| `passkeys_enabled` | true staging, false production | The five management routes mount. A user can enrol, list, rename and delete a passkey, and use one as a second factor |
| `passkeys_passwordless` | true staging, false production | The two `/api/auth/login/passkey/*` routes stop refusing. A passkey becomes a way in with no password at all |

`passkeys_passwordless` is a policy decision, not a rollout step, and stays off
in production until the owner decides. With it off a passkey is a managed
credential and a second factor, which is all the frontend needs.

### RP id and origins

`IDENTITY_RP_ID` comes from `module.identity` and is the registrable domain.
**It is the one identity value that cannot be corrected later**: it is hashed
into every credential and immutable for that credential's life, so a passkey
enrolled under a wrong RP id has to be re-enrolled.
`IDENTITY_WEBAUTHN_ORIGINS` is derived from `local.domain`, the same local
`IDENTITY_FRONTEND_BASE_URL` is built from, so the origin a browser sends and
the origin a ceremony checks cannot drift.

| Environment | RP id | WebAuthn origin |
|---|---|---|
| staging | `staging.webbpulse.com` | `https://staging.webbpulse.com` |
| production | `webbpulse.com` | `https://webbpulse.com` |

The origin is an origin and not a URL with a path, because `clientDataJSON`
carries only scheme, host and port. A passkey enrolled against staging does not
work against production, which is the same property that stops a credential
minted on the real site being replayed from a lookalike.

### Behaviours that present as unexplained refusals

- **A challenge is single use and lasts five minutes.** It is a row, deleted the
  moment it is consumed, and spent by one attempt whatever the outcome. A retry
  needs fresh options.
- **A signature counter that fails to increase is refused and logged at ERROR.**
  The WebAuthn cloned-authenticator signal. Both counts being zero is the
  documented exception and is allowed, since many authenticators keep no counter.
- **A user-verified passkey is not challenged for a TOTP code.** The assertion
  proves possession and `uv` proves the authenticator checked the user, so it
  counts as two factors. A passkey reporting no user verification is one factor.
- **The last passkey cannot be deleted by a user with no password.** It applies
  only to the last one, and "has a password" is read from the `credentials`
  table. Before turning `passkeys_passwordless` on for an account with no
  password, make sure there is a second way in.

### Rolling passkeys back

Set `passkeys_enabled = false` on the environment's workspace and apply. The
seven routes stop being declared on the next cold start. Enrolled credentials
stay in `passkeys` and become reachable again when the variable goes back to
true; the RP id they were enrolled under has not changed. In-flight challenges
expire within five minutes. Nobody is signed out: a session issued by a passkey
login is an ordinary session.
