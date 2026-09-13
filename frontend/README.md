# Frontend

React 19 and TypeScript on Vite, styled with Tailwind CSS. It serves the public
portfolio and blog plus the admin panel that drives every section through the
API.

## Routes

| Path                               | What it is                                      |
| ---------------------------------- | ----------------------------------------------- |
| `/`                                | The portfolio                                   |
| `/blog`, `/blog/:slug`             | The blog index and a post                       |
| `/privacy`                         | The public privacy policy                       |
| `/verify-email`, `/reset-password` | The two identity link pages                     |
| `/admin`                           | The admin panel, the only authenticated surface |

## Getting started

Prerequisites: Node 22, npm, and an AWS login to the WebbPulse Identity Center
for the shared packages.

```bash
npm install       # fetch a CodeArtifact token first, below
npm run dev:local # :5173, proxies /api to localhost:8000
```

### Shared packages from CodeArtifact

`@webbpulse/api-client`, `auth`, `config`, `discovery`, `qrcode`, `tsconfig` and
`eslint-config` are published to CodeArtifact rather than the public registry,
all pinned to `^0.10.2`. `frontend/.npmrc` points the `@webbpulse` scope at that
repository but deliberately holds no token. Before your first install, fetch a
12 hour one:

```bash
AWS_PROFILE=WebbPulse-Artifacts/AdministratorAccess AWS_REGION=us-west-2 \
  aws codeartifact login --tool npm \
    --domain webbpulse --domain-owner 432410731887 \
    --repository npm --namespace @webbpulse
```

That appends the token to `~/.npmrc`, leaving the checked-in `frontend/.npmrc`
untouched. Re-run it when an install starts returning 401.

A `ReadOnlyAccess` profile is not enough: the AWS managed policy omits
`sts:GetServiceBearerToken`, which `codeartifact login` requires. CI does not
use these profiles at all and obtains a token over OIDC.

## Scripts

| Command                          | What it does                                           |
| -------------------------------- | ------------------------------------------------------ |
| `npm run dev:local`              | Dev server on :5173, proxying `/api` to localhost:8000 |
| `npm run dev:remote-api`         | Dev server against `https://api.webbpulse.com/api/v1`  |
| `npm run build`                  | `tsc -b` then a Vite production build                  |
| `npm run lint`, `lint:fix`       | ESLint                                                 |
| `npm run format`, `format:check` | Prettier                                               |
| `npm run test`                   | Vitest in watch mode                                   |
| `npm run test:run`               | Vitest once. CI appends `-- --coverage`                |
| `npm run preview`                | Serve the built bundle                                 |

There is no `npm run dev`. Use `dev:local`.

## Configuration

The bundle's configuration comes from the deploy workflow's build step only.
There is no `.env` file and no Terraform input for it.

| Variable            | Meaning                                                                                               |
| ------------------- | ----------------------------------------------------------------------------------------------------- |
| `VITE_API_BASE_URL` | API base. Set from the environment's `API_BASE_URL`; falls back to `https://api.webbpulse.com/api/v1` |

In local dev Vite proxies `/api/*` to `http://localhost:8000`, so neither needs
setting.

## Auth

Auth is `AuthClient` from `@webbpulse/auth`: an in-memory access token, an
httpOnly refresh cookie, and one retry on a 401. There is no build time switch
and no second mechanism to select.

**Both environments run on identity.** Staging flipped 2026-09-11 02:25Z,
production the same day at 07:18Z. The gateway enforces identity JWTs on the 24
`/api/v1` admin route keys.

The mode used to be chosen by `VITE_AUTH_MODE`, which defaulted to `bearer` when
unset. `deploy-frontend.yml` stopped forwarding it in `ce34362`, so builds after
that commit silently shipped a bearer bundle against JWT enforced routes. The
switch has been removed rather than repaired: `authMode.ts` and
`bearerTokenStore.ts` are gone, `ApiService` always builds an `AuthClient`, and
`getAuthClient` and `getIdentityClient` never return null.

Two guards hold the line. `src/services/api.test.ts` asserts in `built auth
mode` that sign-in goes to `/api/auth/login`, that nothing posts to
`/admin/login`, and that no access token reaches `localStorage`. The
`resolve-env` job in `deploy-frontend.yml` fails the deploy if `frontend/src`
reintroduces `VITE_AUTH_MODE` or the legacy login route.

The backend's `POST /api/v1/admin/login` stays mounted and unused until a later
PR retires it with the `hashed_password` column. Until then, reverting the
frontend to an earlier commit is still a working rollback.

## API layer

Every call goes through `src/services/api.ts` (`apiService`). The transport is
`@webbpulse/api-client` and startup configuration is `@webbpulse/config`. That
client rejects on a non-2xx, so `ApiService` adapts it back into the
`{ data, error }` envelope every page component reads. The envelope is
Portfolio's own and is unchanged.

## Structure

```
src/
├── components/   common, layout and section components
├── pages/        Home, Privacy, VerifyEmail, ResetPassword, NotFound
├── hooks/        custom React hooks
├── services/     api.ts
├── types/        shared TypeScript types
├── utils/        helpers
└── styles/       global styles
```

## Deploys

A push to `staging` or `main` touching `frontend/**` runs `deploy-frontend.yml`,
which resolves the GitHub Environment from the branch and calls the org
`spa-deploy.yml`: CodeArtifact login, `npm run build`, a wait for any active HCP
Terraform run on that workspace, `s3 sync --delete`, then a CloudFront
invalidation. The TFC wait keeps a code deploy from racing an apply.
