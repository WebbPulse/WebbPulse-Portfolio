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

## The two scripts

`backend/scripts/migrate_credentials_to_identity.py` copies each user's bcrypt
hash from the `users` table into the identity `credentials` table, and
`backend/scripts/clear_legacy_credentials.py` removes that column once the copy
is confirmed (PR 174).

Alongside them, the admin seeder became identity aware. That pairing is not
incidental: the seeder used to rewrite `hashed_password` on the first request of
every cold process whenever the column did not verify against `ADMIN_PASSWORD`,
so a column cleared by hand came back within seconds, with a freshly salted hash
that no longer matched the migrated credential. Clearing could not have held
while the seeder looked like that. It now owns the user row and the identity
credential and never the legacy column, so a cleared column stays cleared.

**The hash copies verbatim.** The legacy column and the identity credential are
produced by the same function: `app/core/security.py` `get_password_hash` is a
one line adapter over `webbpulse.security.hash_password`, and the identity
registration flow calls that same function. One bcrypt, cost 12, one encoded
format. So the administrator keeps the password they already have and no
password reset is needed as part of this cutover.

## Where each environment stands today

**Staging is flipped, migrated and cleared.** `AUTH_MODE` was set to `identity`
on 2026-09-11 at 02:25Z, the credential migration applied, and after the
identity sign-in was verified the legacy `hashed_password` column was cleared
from the staging users table with `backend/scripts/clear_legacy_credentials.py`
(PR 174). Steps 1 to 4 are done there.

**Rollback from staging is fix-forward from here.** Step 3 has run, so the
column no longer holds a password the legacy login could verify. Setting
`AUTH_MODE` back to `bearer` in staging would produce a sign-in page nobody can
get past. See "Rolling back" below for what that means in practice.

**Gateway JWT enforcement is live in staging** in `gate` mode (PR 175,
platform-modules 2.9.1), so the staging access gate's Lambda checks the identity
access token as well as the gate's own cookies on the seven routes marked
`require_identity_jwt`. PR 180 added the M5 passkey and M6 OAuth route keys to
the gateway. Production is `off` until the identity stack is promoted there,
because `CreateAuthorizer` fetches the discovery document synchronously and
would fail the apply against an issuer that does not answer yet.

**Production is untouched.** It still runs on `bearer` and repeats the whole
sequence from step 1.

## Order of operations, per environment

Staging first, in full, including a real sign-in through the identity path.
Production repeats the same sequence only after staging is confirmed.

**`--prefix` selects the environment for both scripts, and covers both tables.**
Each script reads two places: the identity `credentials` table, through a store
built from the parsed flag, and the legacy `users` table, through a repository
that reads `settings.DYNAMODB_TABLE_PREFIX` from the environment. The flag used
to reach only the first, so `--prefix webbpulse-staging` on its own read
`webbpulse-development-users` and failed with a ResourceNotFoundException naming
a table nobody had asked for. Both scripts now write the parsed value back into
`DYNAMODB_TABLE_PREFIX` before anything that builds the settings singleton is
imported, so one flag means one environment and no second export is needed.

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

### 3. Clear the legacy credential column

Only after the migration has applied and its output has been read. This is the
step that makes the identity store the only place a password exists, so it is
deliberately separated from the migration by a human verification.

Dry run first, which is the default:

```
cd backend
python scripts/clear_legacy_credentials.py --prefix webbpulse-staging
```

Read the plan, then apply:

```
python scripts/clear_legacy_credentials.py --prefix webbpulse-staging --apply
```

The script removes the attribute only for a user whose identity password
credential holds exactly the hash the legacy column holds. Anything it cannot
account for is a refusal rather than a warning: a `mismatch`, where a credential
exists with a different secret, and a `missing_credential`, where there is none
at all, both stop the run before a single row is written and exit non-zero.
Either one means removing the column would take away a way into the account
without a confirmed replacement. A `mismatch` is usually a password changed
through `POST /api/auth/password` after the migration ran, in which case the
identity store is correct and newer than the column, but the script will not
make that judgement on its own.

No hash is printed, in the summary, a detail line or an error.

**Rollback changes shape after this step.** Up to here, rolling back was a
variable and a redeploy, because the legacy column was still populated and the
legacy routes still read it. Once the column is removed, the legacy login can no
longer authenticate anybody, so rolling back to `bearer` means first
re-migrating from the identity store back into the `users` table. See "Rolling
back" below.

### 4. Flip `VITE_AUTH_MODE` to `identity`

Done in staging on 2026-09-11 at 02:25Z; production still has this ahead of it.
See "The flip" below for the exact change.

Deploy the frontend and sign in. The one time cost the user has already
accepted: **every existing session is signed out once.** The legacy bearer token
lives in `BearerTokenStore` and the identity path never reads it, so the first
page load after the flip has no session and shows the login form. Signing in
once through the identity path is the whole of it.

### 5. Later, in a separate PR: remove the legacy routes

`POST /api/v1/admin/login`, `app/domains/identity/router.py`, the
`hashed_password` column, `BearerTokenStore` and `authMode.ts` go together, once
both environments have run on `identity` long enough to be confident. Until that
PR lands the legacy routes stay mounted, which is what keeps step 4
reversible on the frontend side.

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
the package asks for `openid email profile` at authorisation time.

The consent screen has to exist first, and it requires a reachable privacy
policy URL. That is what `/privacy` serves (PRs 177 and 178): a public,
unauthenticated page on the frontend, linked from the footer. The consent
screens are published, so staging is no longer limited to accounts on a test
user list.

| Environment | Privacy policy URL |
|---|---|
| staging | `https://staging.webbpulse.com/privacy` |
| production | `https://webbpulse.com/privacy` |

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

**None of the seven routes mount until `passkeys_enabled` is true.** Where it
resolves false, the identity function serves exactly the routes it served under
0.14.0 and the OpenAPI document contains no `/api/auth/passkeys` path at all.
That is asserted by `backend/tests/test_identity_m5.py`.

**Both flags are derived from `var.environment` since PR 173, not set in HCP.**
Each is a nullable Terraform variable declared in `terraform/identity.tf` with a
null default, and null means "use the environment's answer": true in staging,
false in production. Two locals resolve them to the explicit bools
`terraform/lambda_domains.tf` renders, so the value that reaches the Lambda
environment is always an explicit bool rather than an omitted one. That matters
because the package's own default for both flags is true, which is the opposite
of what production ships.

The split lives in code rather than in a pair of typed HCP values because every
other per environment decision in this configuration is already a
`var.environment` conditional, and the failure worth guarding against is the
silent one: a promotion to production carrying a staging value nobody remembered
was set. Derived, the environment split is reviewable in the diff and cannot
drift between the two workspaces.

**Setting either variable on a workspace still overrides the derived answer.**
That is what keeps the rollback below a one variable change with no code deploy.

### 1. The two switches are separate, and they are not turned on together

| Variable | Default | Resolves to | What true means |
|---|---|---|---|
| `passkeys_enabled` | `null` | true in staging, false in production | The five management routes mount. A user can enrol, list, rename and delete a passkey, and use one as a second factor. |
| `passkeys_passwordless` | `null` | true in staging, false in production | The two `/api/auth/login/passkey/*` routes stop refusing. A passkey becomes a way into the account with no password at all. |

`passkeys_enabled` was a rollout step that waited on the frontend, and that
precondition is now met: `@webbpulse/auth` 0.8.0 shipped and PR 172 landed the
admin panel code that calls `navigator.credentials.create`, so a mounted route
in staging is a route the frontend actually drives. Production stays off until
the owner promotes it.

`passkeys_passwordless` is a policy decision rather than a rollout step, and it
**stays off in production until the owner decides**. Staging derives it true so
the passwordless path can be exercised against a real authenticator before that
decision is made. Turning it on is not required to use passkeys: with it off a
passkey is a managed credential and a second factor, which is the whole of what
the frontend work needs. The package makes passwordless safe rather than right,
and the difference matters here.
`POST /api/auth/login/passkey/options` answers any input, including an unknown
address, returning a challenge and an empty `allowCredentials` so an anonymous
route cannot become an account oracle. Whether a single administrator product
wants a passwordless entry point at all is a separate question, and nothing in
this PR presumes on the answer.

### 2. Turning passkeys on, per environment

**Staging needs nothing set.** Since PR 173 both flags derive true there, so the
routes are already mounted and no workspace variable is involved.

Promoting to production is a code change rather than an HCP one, because the
derived answer is a `var.environment` conditional in `terraform/identity.tf`.
Leave it there long enough to enrol a passkey and sign in with it on a real
authenticator first, because the failure modes below are the kind that only
appear against a real browser.

To override the derived answer for one environment, set the variable on that
workspace, Terraform kind: `WebbPulse-Portfolio-staging` for staging and
`WebbPulse-Portfolio` for production.

```
passkeys_enabled = true
```

Queue a plan and apply. The plan is a Lambda environment update on the identity
function and nothing else. The routes mount on the next cold start.

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

`GET /api/auth/passkeys/availability` is the eighth route and it is already
there. Added by webbpulse-python 0.17.0, it mounts in every deployment
regardless of either variable and answers
`{"enabled": <bool>, "passwordless": <bool>}` from exactly the two settings
above, with `Cache-Control: public, max-age=300`. It is what the frontend reads
to decide what to draw, so on the day either variable is flipped the answer
changes with it and the affordance appears within five minutes.

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

### 5. What the admin panel shows

The frontend part of passkeys ships ahead of the backend adoption, in the same
shape the OAuth work shipped: the UI is written and tested, and it shows nothing
at all until a deployment says it has the capability. The login page asks the
same way the OAuth buttons ask, by reading a discovery route:
`GET /api/auth/passkeys/availability` answers two booleans, and the sign-in
button is drawn only when `passwordless` is true.

The two fields are different questions. `enabled` means the deployment registers
and verifies passkeys, so the settings panel offers to add one. `passwordless`
means a passkey is a way *into* an account, so the sign-in page offers the
button. With `enabled` true and `passwordless` false a passkey is a managed
credential and a second factor but not an entry point, which is the state
production starts in.

Until webbpulse-python 0.17.0 there was no such route and the login page probed
`POST /api/auth/login/passkey/options` instead, reading a 404 or a
`PASSKEYS_DISABLED` or `PASSKEY_LOGIN_DISABLED` refusal as "not offered here".
That is gone. The probe spent one of the options route's thirty calls per
fifteen minutes per IP on a sign-in *page load* rather than on a sign-in, so a
user who reloaded enough times was refused the passkey sign-in they were
reloading in order to attempt, and it wrote a WebAuthn challenge row per call
that was never spent. The route that replaced it is anonymous, unrated, touches
no store and is cached for five minutes by the browser. The answer is fetched
once per page load, coalesced across the components that ask on the same paint.

#### What a signed-in admin sees

A **Passkeys** panel in the Security section of the admin panel, above Connected
accounts. It lists each passkey with the name it was given, when it was added
and when it was last used, and it offers three things:

- **Add a passkey.** The form prefills a name from the platform the browser
  reports, so a Mac offers "Mac" and an iPhone offers "iPhone", and the name is
  editable before the browser prompt opens. Dismissing that prompt closes the
  form and says nothing: changing your mind is not an error.
- **Rename.** The row is patched from the response rather than the whole list
  being reloaded.
- **Remove**, behind an inline confirmation, because a removed passkey cannot be
  recovered.

Removal is the one operation the server can refuse for a reason the panel has to
explain. An account whose only way in is a single passkey cannot delete it, and
that refusal disables the Remove control on that row and prints the reason
underneath it, naming the remedy: set a password first, or add a second passkey.
The block is held per passkey, so enrolling a second one re-enables the first
one's Remove without a reload.

A deployment where the routes are not mounted renders one sentence saying so,
rather than an empty panel that looks like an account with nothing enrolled.

#### What a signed-out visitor sees

A **Sign in with a passkey** button under the password form, next to the OAuth
buttons, when all three of these are true: the build is in `identity` mode, the
browser supports WebAuthn, and the availability route above answered
`passwordless: true`. It is a button rather than a link because the ceremony is
a script call that needs a user gesture.

Where the browser also supports conditional mediation, the page starts a second,
invisible ceremony on load and marks the username field `username webauthn`, so
a saved passkey is offered in the field's own autofill list. That ceremony is
aborted when the password form is submitted, so a password sign-in and a passkey
sign-in can never race for the same session.

A passkey sign-in that verified the user carries that fact in the token's `amr`,
so an account with TOTP enrolled is not asked for a code as well. An
authenticator that did not verify the user is one factor, and the code step still
runs.

#### Browser support

WebAuthn is a secure context API, so it exists on HTTPS and on `localhost` and
nowhere else. Safari 16 and later, Chrome and Edge 108 and later, and Firefox
119 and later all have what this UI uses. Conditional mediation is the newer
half and is absent in some of those versions; where it is missing the button
still works and only the autofill offer is skipped. Everything is feature
detected rather than sniffed, so a browser that cannot do it is shown nothing
rather than a control that throws when pressed.

### 6. Rolling passkeys back

Set the variable on the environment's workspace, which overrides the derived
answer, and apply:

```
passkeys_enabled = false
```

That is the rollback for staging, where the derived answer is true: one HCP
variable, no code deploy.

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

**That is the whole rollback only before step 3 has run.** Up to that point the
legacy routes are still mounted, the `hashed_password` column is still
populated, and the migration only ever added rows to a table the legacy path
does not read, so nothing needs undoing on the backend. The cost is symmetric
with the flip: one more forced sign-in.

**After step 3 the column is gone**, and the legacy login verifies every
password against a dummy hash, so it refuses everybody rather than erroring.
Setting the variable back therefore produces a sign-in page nobody can get past.
Rolling back from there means first re-migrating in the other direction, writing
each user's secret from the identity `credentials` table back onto the `users`
row, and there is deliberately no script for that: the identity store is the
system of record from step 3 onward, and the intended way out of a problem after
it is to fix forward rather than to repopulate a column that is being retired.

Once the legacy routes are removed in step 5 this rollback stops working
entirely, which is why that removal waits for both environments to be settled.
