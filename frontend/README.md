# WebbPulse Portfolio Website

A modern, responsive personal portfolio website showcasing development work and skills, built with TypeScript React and Tailwind CSS.

## 🚀 Tech Stack

- **Frontend**: React 19 with TypeScript
- **Build Tool**: Vite with SWC for fast compilation
- **Styling**: Tailwind CSS
- **Package Manager**: npm
- **Development**: Hot Module Replacement (HMR)

## 📦 Getting Started

### Prerequisites

- Node.js 18+
- npm
- AWS CLI, signed in to the WebbPulse Identity Center, for the shared packages

### Shared packages from CodeArtifact

This frontend depends on the org's shared TypeScript packages, which are
published to AWS CodeArtifact rather than the public npm registry:

| Package                    | Used for                                               |
| -------------------------- | ------------------------------------------------------ |
| `@webbpulse/api-client`    | The typed fetch client behind `src/services/api.ts`    |
| `@webbpulse/auth`          | `AuthClient`, for the identity mode described below    |
| `@webbpulse/config`        | Validated startup configuration from `import.meta.env` |
| `@webbpulse/tsconfig`      | The compiler options `tsconfig.app.json` extends       |
| `@webbpulse/eslint-config` | The lint rules `eslint.config.js` extends              |

`frontend/.npmrc` points the `@webbpulse` scope at the CodeArtifact repository,
but it deliberately holds no auth token. Before your first `npm install` or
`npm ci`, fetch a 12 hour token:

```bash
AWS_PROFILE=WebbPulse-Artifacts/AdministratorAccess AWS_REGION=us-west-2 \
  aws codeartifact login --tool npm \
    --domain webbpulse --domain-owner 432410731887 \
    --repository npm --namespace @webbpulse
```

That appends the token to your `~/.npmrc`, leaving the checked in
`frontend/.npmrc` untouched. Re-run it when an install starts returning 401.

Note that a `ReadOnlyAccess` profile is not enough: the AWS managed
ReadOnlyAccess policy omits `sts:GetServiceBearerToken`, which
`codeartifact login` requires. CI does not use these profiles at all; it obtains
a token over OIDC in the workflow.

### Authentication modes

Authentication is mid migration, and which mechanism a bundle uses is chosen by
the `VITE_AUTH_MODE` environment variable rather than by a code change.

| Mode               | What it does                                                                                                        |
| ------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `bearer` (default) | `POST /api/v1/admin/login` answers with a bearer token, which is held in `localStorage` and sent on every request   |
| `identity`         | `AuthClient` from `@webbpulse/auth`: an in memory access token, an httpOnly refresh cookie, and retry once on a 401 |

**Staging runs on `identity`.** The flip happened on 2026-09-11 at 02:25Z, and
the legacy `hashed_password` column was cleared from the staging users table
after the identity sign-in was verified (PR 174). Production still builds
`bearer`.

The identity routes `AuthClient` needs are live: `/api/auth/login`,
`/api/auth/refresh` and `/api/auth/logout`, alongside email verification and
password reset (M3), TOTP and recovery codes (M4), passkeys (M5) and OAuth
sign-in with Google and GitHub (M6). Setting `VITE_AUTH_MODE=identity` on an
environment whose backend has not been promoted still breaks signing in, which
is the only reason production has not been flipped.

Once every environment carries it, the bearer branch in `src/services/api.ts`,
`src/services/bearerTokenStore.ts` and `src/services/authMode.ts` are deleted
together. See `IDENTITY_CUTOVER` in `src/services/api.ts` for the full list of
what the backend has to provide, and `docs/identity-cutover.md` for the runbook.

### Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd Portfolio-Website
```

2. Log in to CodeArtifact, as above, then install dependencies:

```bash
npm install
```

3. Start the development server:

```bash
npm run dev
```

4. Open your browser and navigate to `http://localhost:5173`

## 🛠️ Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run lint` - Run ESLint
- `npm run preview` - Preview production build

## 📁 Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── common/         # Common components (Button, Card, etc.)
│   ├── layout/         # Layout components (Header, Footer, etc.)
│   └── sections/       # Page sections (Hero, About, etc.)
├── pages/              # Page components
├── hooks/              # Custom React hooks
├── utils/              # Utility functions
├── types/              # TypeScript type definitions
├── assets/             # Static assets
└── styles/             # Global styles
```

## 🎨 Design System

- **Theme**: Modern dark color scheme
- **Colors**: Gray scale with blue accents
- **Typography**: System fonts with responsive sizing
- **Layout**: Responsive grid system with Tailwind CSS

## 🚀 Development Plan

The original 10-phase build plan is complete: the site is built, deployed and
serving production traffic on S3, CloudFront and Route 53, with GitHub Actions
deploying both halves. Current work is the identity migration described below.

## 📋 Current Status

The site is live. Public routes are `/` (the portfolio itself), `/blog` and
`/blog/:slug`, `/privacy` (the public privacy policy, PRs 177 and 178), and the
two identity link pages `/verify-email` and `/reset-password`. `/admin` is the
admin panel and is the only authenticated surface.

The identity migration is the active workstream, tracked by milestone against
the backend's `@webbpulse/*` adoption. What has landed on `staging`:

| Milestone | What the admin panel gained | PRs |
| --- | --- | --- |
| Shared packages | `@webbpulse/*` 0.4.0, then 0.5.0 | 159, 165 |
| M2 sessions | The identity sign-in path behind `VITE_AUTH_MODE` | 159, 160 |
| M3 links | The `/verify-email` and `/reset-password` pages | 162, 165 |
| M4 MFA | The TOTP and recovery code management surface | 166, 167, 168 |
| M6 OAuth | Google and GitHub sign-in buttons | 169, 170 |
| M5 passkeys | Passkey sign-in and the Passkeys management panel | 171, 172, 173 |
| Privacy policy | The public `/privacy` page | 177, 178 |

Passkeys and passwordless sign-in are both on in staging and off in production,
derived from the environment rather than set per workspace (PR 173). Gateway
JWT enforcement is live in staging in `gate` mode (PR 175), with the passkey and
OAuth route keys declared in PR 180. The M0 identity spike was retired in
PR 176.

Still ahead: promoting the identity stack to production, flipping
`VITE_AUTH_MODE` there, and then deleting the bearer branch.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Contact

- **Website**: [webbpulse.com](https://webbpulse.com)
- **Privacy policy**: [webbpulse.com/privacy](https://webbpulse.com/privacy)

---

Built with ❤️ using React, TypeScript, and Tailwind CSS
