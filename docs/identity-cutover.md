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
