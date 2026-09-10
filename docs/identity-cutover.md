# Identity cutover runbook

How Portfolio moves from its legacy bearer token login to the shared identity
standard, one environment at a time.

The cutover is deliberately made of small, separately reversible steps. Nothing
below deletes the legacy login, so every step up to and including the flip can
be undone by changing one variable and redeploying.

## What is already in place

- **M2 adoption** (PR 160) put the identity Lambda in staging with the
  `credentials`, `refresh-tokens` and `login-attempts` tables and the six POST
  routes under `/api/auth`.
- **The frontend already supports both modes** (PR 159).
  `frontend/src/services/authMode.ts` reads `VITE_AUTH_MODE`, accepts `bearer`
  or `identity`, and defaults to `bearer` when the variable is absent. Both
  paths are written and typed; selecting one is a build time decision, not a
  code change.

## What this PR adds

`backend/scripts/migrate_credentials_to_identity.py`, which copies each user's
bcrypt hash from the `users` table into the identity `credentials` table.

**The hash copies verbatim.** The legacy column and the identity credential are
produced by the same function: `app/core/security.py` `get_password_hash` is a
one line adapter over `webbpulse.security.hash_password`, and the identity
registration flow calls that same function. One bcrypt, cost 12, one encoded
format. So the administrator keeps the password they already have and no
password reset is needed as part of this cutover.

## Order of operations, per environment

Staging first, in full, including a real sign-in through the identity path.
Production repeats the same sequence only after staging is confirmed.

### 1. M3 adoption is applied

The identity Lambda is live and the six routes answer. Confirm with an
unauthenticated probe, which should be a 401 rather than a 404 or a 5xx:

```
curl -si https://api.staging.webbpulse.com/api/auth/login \
  -H 'content-type: application/json' -d '{}' | head -1
```

### 2. Run the credential migration, dry run first

The script is dry run by default and writes nothing without `--apply`. Run it
with credentials for the target account and the environment's table prefix.

```
cd backend
python scripts/migrate_credentials_to_identity.py --prefix webbpulse-staging
```

Read the plan. For Portfolio it should be exactly one user with the action
`write`. Then apply:

```
python scripts/migrate_credentials_to_identity.py --prefix webbpulse-staging --apply
```

The script is idempotent, so a rerun after a partial failure is safe: a
credential that already matches the legacy hash is reported `unchanged` and left
alone, `created_at` included.

If it reports a `conflict`, stop. That means a credential exists whose secret is
not the legacy hash, which is either a password changed through the identity
flow or a run pointed at the wrong environment. `--replace` overwrites from the
users table and is the right answer only once you know which of the two it is.

### 3. Flip `VITE_AUTH_MODE` to `identity`

Not done in this PR. See "The flip" below for the exact change.

Deploy the frontend and sign in. The one time cost the user has already
accepted: **every existing session is signed out once.** The legacy bearer token
lives in `BearerTokenStore` and the identity path never reads it, so the first
page load after the flip has no session and shows the login form. Signing in
once through the identity path is the whole of it.

### 4. Later, in a separate PR: remove the legacy routes

`POST /api/v1/admin/login`, `app/domains/identity/router.py`, the
`hashed_password` column, `BearerTokenStore` and `authMode.ts` go together, once
both environments have run on `identity` long enough to be confident. Until that
PR lands the legacy routes stay mounted and keep working, which is what makes
step 3 reversible.

## The flip

Two changes, because the workflow passes VITE variables through explicitly.

**1. `.github/workflows/deploy-frontend.yml`** does not forward `VITE_AUTH_MODE`
today. Its `Build` step passes only `VITE_API_BASE_URL`. Add the variable to
that step's `env`:

```yaml
      - name: Build
        working-directory: frontend
        env:
          VITE_API_BASE_URL: ${{ vars.API_BASE_URL != '' && format('{0}/api/v1', vars.API_BASE_URL) || '' }}
          VITE_AUTH_MODE: ${{ vars.AUTH_MODE }}
        run: npm run build
```

An unset `vars.AUTH_MODE` renders as an empty string, and `ConfigReader.oneOf`
falls back to `bearer` for it, so adding this line alone changes nothing until
the variable is set.

**2. Set the `AUTH_MODE` GitHub Environment variable to `identity`.** The
workflow selects the environment from the branch: `staging` for the `staging`
branch and `production` for `main` (`deploy-frontend.yml`, the `environment:`
key). So the per environment flip is:

```
gh variable set AUTH_MODE --env staging    --body identity --repo WebbPulse/WebbPulse-Portfolio
gh variable set AUTH_MODE --env production --body identity --repo WebbPulse/WebbPulse-Portfolio
```

Then rerun the frontend deploy for that branch, since the variable is read at
build time and the currently deployed bundle already has the old value baked in.

There is no `.env` file in `frontend/` and no Terraform input for this: the
bundle's configuration comes from the workflow's build step only.

## Two factor authentication, once M4 is applied

M4 adds six routes under `/api/auth` and two DynamoDB tables, `totp-factors` and
`recovery-codes`. Nothing about signing in changes for anybody until an
individual account enrols: a login for a user with no active factor answers
exactly as it did before. Enrolment is per account and opt in, and there is no
policy that requires it.

### What an admin does to enrol

The backend half of this is what M4 ships. The screens that drive it are a
separate frontend PR, so until that lands the sequence below is what the
frontend will call rather than something a person can click.

1. **Sign in normally.** Enrolment is a step up operation, so it needs a session
   that already exists. `POST /api/auth/step-up` is what raises a plain session
   to one allowed to change a factor, and the enrolment routes require it.
2. **`POST /api/auth/totp/enrol`** returns a new seed as an `otpauth://` URI and
   its matching QR payload. The seed is generated on the server, sealed with the
   KMS envelope key before it is written, and returned exactly once. Nothing
   reads it back afterwards, so an admin who closes the screen at this point
   starts over rather than recovering it.
3. **Scan the QR into an authenticator app**, then submit the six digit code it
   shows to **`POST /api/auth/totp/activate`**. The factor is inactive until this
   succeeds, which is what stops a mis-scanned seed from locking anybody out: a
   failed activation leaves the account exactly as it was.
4. **Store the recovery codes** the activation response returns. See below.

From then on that account's `POST /api/auth/login` answers with an MFA challenge
instead of a session, and the second step is `POST /api/auth/login/totp` carrying
the ticket from the challenge plus a code. `POST /api/auth/totp/disable` removes
the factor and returns the account to single factor. As of package 0.13.0 it
requires `{"code": "..."}` in the body as well as the bearer token: a current
TOTP code or an unused recovery code, verified before anything is deleted.

### Where recovery codes are shown

**Once, in the response to `POST /api/auth/totp/activate`, and never again.**
Only a hash of each code is stored, in the `recovery-codes` table keyed on the
user and the code hash, so the server cannot redisplay them and neither can
anybody with database access. An admin who loses them has one option, which is
`POST /api/auth/recovery-codes` carrying `{"code": "..."}`: it issues a fresh set
and invalidates every previous code in the same write. As of package 0.13.0 that
body is required and is a current TOTP code or an unused recovery code, not a
stepped up session. There is deliberately no step-up alternative on either
route, because accepting a recently stepped up access token would reintroduce
the bearer-token-only path the code requirement exists to close. Verification
happens before the old set is deleted, so a refused attempt leaves every
existing code working.

Each code is single use. Spending one at the second login step deletes its row,
and codes do not expire, which is deliberate: a recovery code is the thing an
admin reaches for months after enrolment, when the phone is gone, and one that
had quietly expired would be worse than none at all.

The practical guidance for a Portfolio administrator is to put the codes in
1Password alongside the account, not in the same authenticator app that holds
the factor. The failure they exist for is losing that app.

### The seed at rest

The seed is never stored in plaintext. `MfaService` seals it with an envelope:
KMS `GenerateDataKey` under the identity module's TOTP key, with an encryption
context of `purpose=totp` and the user id, so a sealed seed lifted from one row
cannot be unsealed as another user's. The key ARN reaches the function as
`IDENTITY_DATA_KEY_ARN`, set by the identity module. A deployment where that
variable is missing still serves all six routes and fails at the first enrolment
with an error naming the variable, rather than hiding the routes.

## OAuth providers, once M6 is applied

M6 adds five routes under `/api/auth/oauth` and four DynamoDB tables:
`oauth-states`, `oauth-links` and, ahead of M5, `passkeys` and
`webauthn-challenges`. The tables are created by this apply, but **none of the
five routes mount until a provider client id is configured**. With both client
id variables empty, which is how this PR ships, the identity function serves
exactly the routes it served before and the OpenAPI document contains no
`/api/auth/oauth` path at all. That is asserted by
`backend/tests/test_identity_m6.py`, so applying this PR changes no behaviour
that anybody can reach.

Turning a provider on is therefore a configuration change and not a code change.
What follows is the owner's part of it.

### 1. Register the applications

Two things have to be created by hand, one per provider. Neither can be created
by Terraform: both consoles are outside AWS and neither has an API this project
is set up to call.

**Google.** In the Google Cloud console, under **APIs and Services, Credentials**
of the project that owns the sign in, create an **OAuth client ID** of type
**Web application**. Give it the authorised redirect URI for the environment from
the table below, and nothing else. It needs no scopes configured in the console:
the package asks for `openid email profile` at authorisation time. The consent
screen has to exist first, and while it is in testing mode only accounts on its
test user list can sign in, which is a reasonable place to leave staging.

**GitHub.** Under **Settings, Developer settings, OAuth Apps**, create a **New
OAuth App**. The **Authorization callback URL** is the same redirect URI from the
table below. GitHub allows exactly one callback URL per app, so staging and
production need two separate apps. Nothing else on the form matters to this
backend.

### 2. Redirect URI, per environment

The redirect URI is derived in Terraform from the identity issuer, so it is not
a value anybody types into HCP. It is the value to paste into both provider
consoles:

| Environment | Redirect URI |
|---|---|
| staging | `https://api.staging.webbpulse.com/api/auth/oauth/callback` |
| production | `https://api.webbpulse.com/api/auth/oauth/callback` |

Both are `${local.identity_issuer}/oauth/callback`, and `local.identity_issuer`
is built from `local.api_host`, which is the custom hostname in both
environments and does not change shape with `staging_profile`. The workspace
output `identity_issuer` is the authoritative value if either ever moves.

Both providers match this string exactly, including the scheme and any trailing
character, and a mismatch is a provider error page rather than anything this
backend logs.

### 3. Where the id and the secret go

The two halves go to different places on purpose. A client id is public, appears
in the authorisation URL a browser follows, and is a plain Terraform variable. A
client secret is not, and never becomes an environment variable on the function.

| Value | Where it goes | Name |
|---|---|---|
| Google client id | HCP Terraform workspace variable, Terraform category, not sensitive | `oauth_google_client_id` |
| GitHub client id | HCP Terraform workspace variable, Terraform category, not sensitive | `oauth_github_client_id` |
| Google client secret | key in the per environment `app` JSON secret | `oauth_google_client_secret` |
| GitHub client secret | key in the per environment `app` JSON secret | `oauth_github_client_secret` |

The workspace variables are `WebbPulse-Portfolio-staging` and
`WebbPulse-Portfolio`. Both client id variables default to the empty string, so a
workspace that has never had them set plans and applies cleanly, and setting one
later is a one line plan against the identity function's environment.

The secret is `webbpulse-<env>/app`, the single JSON secret this service already
reads through `APP_SECRETS_ARN`. Add the two keys to the existing document
rather than creating a new secret. The backend reads them optionally: a document
with neither key present yields an empty mapping and the routes stay unmounted,
which is exactly the state before step 1.

### 4. What to expect after setting them

Setting a client id alone mounts the routes. Setting it **without** the matching
secret mounts routes that will fail the token exchange at the provider, so set
the secret first, then the variable, then apply. The apply is a Lambda
environment update and a new deployment picks the secret up on its next cold
start, since the secret document is cached for the life of an execution
environment.

`GET /api/auth/oauth/links` lists the links on the signed in account and
`DELETE /api/auth/oauth/{provider}/link` removes one. Unlinking is refused when
it would leave an account with no way back in; see
`has_other_sign_in_method` in `backend/app/composition/identity_hooks.py` for how
Portfolio answers that question today and why.

## Passkeys, once M5 is applied

M5 adds seven routes under `/api/auth` and needs no new table: `passkeys` and
`webauthn-challenges` were created by the M6 apply, ahead of the code that reads
them, so adopting M5 is a backend change with no apply in front of it.

**None of the seven routes mount until `passkeys_enabled` is true.** With it
false, which is how this PR ships in both environments, the identity function
serves exactly the routes it served under 0.14.0 and the OpenAPI document
contains no `/api/auth/passkeys` path at all. That is asserted by
`backend/tests/test_identity_m5.py`, so applying this PR changes no behaviour
that anybody can reach.

**The package's own default for both passkey flags is true, and this product
ships both false.** That inversion is the one thing about this milestone worth
reading twice, because it means an omitted Terraform variable is not a no-op:
it would mount seven routes. Both are set explicitly in
`terraform/lambda_domains.tf` for that reason, and a test pins the package
default so a future release that flips it turns the now-redundant line into a
failing test rather than a line nobody can explain.

### 1. The two switches are separate, and they are not turned on together

| Variable | Default | What true means |
|---|---|---|
| `passkeys_enabled` | `false` | The five management routes mount. A user can enrol, list, rename and delete a passkey, and use one as a second factor. |
| `passkeys_passwordless` | `false` | The two `/api/auth/login/passkey/*` routes stop refusing. A passkey becomes a way into the account with no password at all. |

`passkeys_enabled` is a rollout step and waits on the frontend.
`@webbpulse/auth` 0.8.0 is what calls `navigator.credentials.create`, and until
it ships a mounted route is a route nothing calls, and one a curious client
could enrol a credential against under an RP id that is immutable for that
credential's life.

`passkeys_passwordless` is a policy decision rather than a rollout step, and it
**stays off until the owner decides**. Turning it on is not required to use
passkeys: with it off a passkey is a managed credential and a second factor,
which is the whole of what the frontend work needs. The package makes
passwordless safe rather than right, and the difference matters here.
`POST /api/auth/login/passkey/options` answers any input, including an unknown
address, returning a challenge and an empty `allowCredentials` so an anonymous
route cannot become an account oracle. Whether a single administrator product
wants a passwordless entry point at all is a separate question, and nothing in
this PR presumes on the answer.

### 2. Turning passkeys on, per environment

Both are HCP Terraform workspace variables, Terraform kind, on the workspace for
the environment: `WebbPulse-Portfolio-staging` for staging and
`WebbPulse-Portfolio` for production.

```
passkeys_enabled = true
```

Set it, queue a plan, and apply. The plan is a Lambda environment update on the
identity function and nothing else. The routes mount on the next cold start.

Staging first, and leave it there long enough to enrol a passkey and sign in
with it on a real authenticator, because the failure modes below are the kind
that only appear against a real browser.

### 3. What the RP id and the origins have to agree about

Two values decide whether a ceremony can succeed at all, and neither is typed
into HCP.

`IDENTITY_RP_ID` comes from `module.identity` and is the registrable domain,
the same string the refresh cookie is scoped to. **It is the one identity value
that cannot be corrected later**: it is hashed into every credential and
immutable for that credential's life, so a passkey enrolled under a wrong RP id
has to be re-enrolled rather than fixed by a variable change.

`IDENTITY_WEBAUTHN_ORIGINS` is derived in Terraform from `local.domain`, the
same local `IDENTITY_FRONTEND_BASE_URL` is built from, so the origin a browser
sends and the origin a ceremony checks cannot drift apart.

| Environment | RP id | WebAuthn origin |
|---|---|---|
| staging | `staging.webbpulse.com` | `https://staging.webbpulse.com` |
| production | `webbpulse.com` | `https://webbpulse.com` |

The origin is an origin and not a URL with a path, because `clientDataJSON`
carries only the scheme, host and port. The package requires both values rather
than defaulting either, and raises naming the variable when one is missing: an
empty origin list would make the origin check vacuous, and the origin check is
the whole of what makes a passkey phishing resistant.

A passkey enrolled against staging does not work against production, and that is
correct rather than an inconvenience. The two are different RP ids, which is the
same property that stops a credential minted on the real site being replayed
from a lookalike.

### 4. What to expect after setting it

The five management routes appear first, and they are the ones the frontend
needs: `POST /api/auth/passkeys/register/options` and `.../verify` to enrol,
`GET /api/auth/passkeys` to list, and `PATCH` and `DELETE` on
`/api/auth/passkeys/{credential_id}` to rename and remove one.

The two login routes mount at the same time and refuse while
`passkeys_passwordless` is false, which is the intended state. They start
working on the day that second variable is set, with no code change and no
redeploy beyond the apply.

Three package behaviours worth knowing before the first real sign in, because
each presents as a refusal with no obvious cause:

- **A challenge is single use and lasts five minutes.** It is a row, deleted the
  moment it is consumed, and spent by one attempt whatever the outcome. A retry
  needs fresh options rather than a replayed challenge.
- **A signature counter that fails to increase is refused and logged at ERROR.**
  That is the WebAuthn specification's cloned-authenticator signal. Both counts
  being zero is the documented exception and is allowed, because many
  authenticators, Apple's included, keep no counter at all.
- **A user-verified passkey is not challenged for a TOTP code.** The assertion
  proves possession and the `uv` flag proves the authenticator checked something
  the user knows or is, so it counts as two factors. A passkey that reports no
  user verification is one factor and is challenged for a second exactly as a
  password is.

And one that matters for account recovery: **the last passkey cannot be deleted
by a user with no password.** It applies only to the last one, and "has a
password" is read from the `credentials` table. Before turning
`passkeys_passwordless` on for an account that has no password set, make sure
there is a second way in.

### 5. Rolling passkeys back

Set the variable back and apply:

```
passkeys_enabled = false
```

The seven routes stop being declared on the next cold start. Nothing needs
undoing in the data: enrolled credentials stay in `passkeys` and become
reachable again the moment the variable goes back to true, and the RP id they
were enrolled under has not changed. Any in-flight challenges expire on their
own within five minutes.

Turning it off does not sign anybody out. A session issued by a passkey login is
an ordinary session and is unaffected.

## Rolling back

Set the variable back and redeploy:

```
gh variable set AUTH_MODE --env staging --body bearer --repo WebbPulse/WebbPulse-Portfolio
```

That is the whole rollback. The legacy routes are still mounted, the
`hashed_password` column is still populated, and the migration only ever added
rows to a table the legacy path does not read, so nothing needs undoing on the
backend. The cost is symmetric with the flip: one more forced sign-in.

Once the legacy routes are removed in step 4 this rollback stops working, which
is why that removal waits for both environments to be settled.
