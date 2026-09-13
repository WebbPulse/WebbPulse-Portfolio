# Frontend

React 19 and TypeScript on Vite, styled with Tailwind CSS. It serves the public
portfolio and blog plus the admin panel that drives every section through the
API.

## Routes

| Path | What it is |
| --- | --- |
| `/` | The portfolio |
| `/blog`, `/blog/:slug` | The blog index and a post |
| `/privacy` | The public privacy policy |
| `/verify-email`, `/reset-password` | The two identity link pages |
| `/admin` | The admin panel, the only authenticated surface |

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

| Command | What it does |
| --- | --- |
| `npm run dev:local` | Dev server on :5173, proxying `/api` to localhost:8000 |
| `npm run dev:remote-api` | Dev server against `https://api.webbpulse.com/api/v1` |
| `npm run build` | `tsc -b` then a Vite production build |
| `npm run lint`, `lint:fix` | ESLint |
| `npm run format`, `format:check` | Prettier |
| `npm run test` | Vitest in watch mode |
| `npm run test:run` | Vitest once. CI appends `-- --coverage` |
| `npm run preview` | Serve the built bundle |

There is no `npm run dev`. Use `dev:local`.

## Configuration

The bundle's configuration comes from the deploy workflow's build step only.
There is no `.env` file and no Terraform input for it.

| Variable | Meaning |
| --- | --- |
| `VITE_API_BASE_URL` | API base. Set from the environment's `API_BASE_URL`; falls back to `https://api.webbpulse.com/api/v1` |
| `VITE_AUTH_MODE` | `bearer` or `identity`. Absent means `bearer` |

In local dev Vite proxies `/api/*` to `http://localhost:8000`, so neither needs
setting.

## Auth

Both mechanisms are written and tested, and `src/services/authMode.ts` selects
one at build time from `VITE_AUTH_MODE`.

| Mode | What it does |
| --- | --- |
| `bearer` | `POST /api/v1/admin/login` returns a token held in `localStorage` by `src/services/bearerTokenStore.ts` |
| `identity` | `AuthClient` from `@webbpulse/auth`: an in-memory access token, an httpOnly refresh cookie, and one retry on a 401 |

**Both environments run on `identity`.** Staging flipped 2026-09-11 02:25Z,
production the same day at 07:18Z. The gateway enforces identity JWTs on the 24
`/api/v1` admin route keys, so a bundle built in `bearer` mode cannot make admin
writes against either environment.

> **Open defect.** `deploy-frontend.yml` no longer forwards `VITE_AUTH_MODE`
> into the build, so the next frontend deploy would rebuild in `bearer` mode and
> break admin writes. See `docs/identity-cutover.md`, "Open defect", before
> triggering one.

The bearer branch in `src/services/api.ts`, `bearerTokenStore.ts` and
`authMode.ts` is deleted together with the backend's legacy login, once both
environments have run on identity long enough. Keeping it is what leaves the
flip reversible.

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
├── services/     api.ts, authMode.ts, bearerTokenStore.ts
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
