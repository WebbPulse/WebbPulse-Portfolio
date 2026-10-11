# Frontend

React 19 and TypeScript on Vite, styled with Tailwind CSS. It serves the public
portfolio and blog. Content lives in typed files under `src/content/`; there
is no admin panel and no sign-in.

## Routes

| Path                   | What it is                                    |
| ---------------------- | --------------------------------------------- |
| `/`                    | The portfolio                                 |
| `/blog`, `/blog/:slug` | The blog index and a post                     |
| `/privacy`             | The public privacy policy                     |
| anything else          | The 404 page, `/admin` included               |

## Getting started

Prerequisites: Node 22, npm, and an AWS login to the WebbPulse Identity Center
for the shared packages.

```bash
npm install       # fetch a CodeArtifact token first, below
npm run dev:local # :5173, proxies /api to localhost:8000
```

### Shared packages from CodeArtifact

`@webbpulse/api-client`, `config`, `tsconfig` and `eslint-config` are
published to CodeArtifact rather than the public registry. `frontend/.npmrc` points the `@webbpulse` scope at that
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

| Command                          | What it does                                                    |
| -------------------------------- | --------------------------------------------------------------- |
| `npm run dev:local`              | Dev server on :5173, proxying `/api` to localhost:8000          |
| `npm run dev:remote-api`         | Dev server against `https://api.portfolio.webbpulse.com/api/v1` |
| `npm run build`                  | `tsc -b` then a Vite production build                           |
| `npm run lint`, `lint:fix`       | ESLint                                                          |
| `npm run format`, `format:check` | Prettier                                                        |
| `npm run test`                   | Vitest in watch mode                                            |
| `npm run test:run`               | Vitest once. CI appends `-- --coverage`                         |
| `npm run preview`                | Serve the built bundle                                          |

There is no `npm run dev`. Use `dev:local`.

## Configuration

The bundle's configuration comes from the deploy workflow's build step only.
There is no `.env` file and no Terraform input for it.

| Variable            | Meaning                                                                                                         |
| ------------------- | --------------------------------------------------------------------------------------------------------------- |
| `VITE_API_BASE_URL` | API base. Set from the environment's `API_BASE_URL`; falls back to `https://api.portfolio.webbpulse.com/api/v1` |

In local dev Vite proxies `/api/*` to `http://localhost:8000`, so neither needs
setting.

## API layer

`src/services/api.ts` (`apiService`) holds only the anonymous
`getPublicFigures()` read. The transport is `@webbpulse/api-client` and startup
configuration is `@webbpulse/config`. That client rejects on a non-2xx, so
`ApiService` adapts it back into Portfolio's own `{ data, error }` envelope.

## Structure

```
src/
├── components/   common, layout and section components
├── pages/        Home, Privacy, NotFound
├── hooks/        custom React hooks
├── services/     api.ts
├── types/        shared TypeScript types
├── utils/        helpers
└── styles/       global styles
```

## Deploys

A push to `staging` or `main` touching `frontend/**` runs `deploy-frontend.yml`,
which resolves the GitHub Environment from the branch and calls the org
`spa-deploy.yml@v3`: CodeArtifact login, `npm run build`, `s3 sync --delete`, then
a CloudFront invalidation. It does not wait on HCP Terraform: applies are confirmed
by hand and never auto-run, so a deploy cannot race one.
