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

`identity` is written, typed and unit tested today, but it is not switched on
because the routes it calls do not exist yet. Portfolio's identity function
currently serves the JWKS, the OpenID discovery document and its own health
route; `AuthClient` additionally needs `/api/auth/login`, `/api/auth/refresh`
and `/api/auth/logout`. Setting `VITE_AUTH_MODE=identity` before those are live
breaks signing in.

When they are live, set `VITE_AUTH_MODE=identity` on the environment. Once
every environment carries it, the bearer branch in `src/services/api.ts`,
`src/services/bearerTokenStore.ts` and `src/services/authMode.ts` are deleted
together. See `IDENTITY_CUTOVER` in `src/services/api.ts` for the full list of
what the backend has to provide.

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

This project follows a 10-week development plan with the following phases:

1. ✅ **Project Setup & Foundation** - Vite, React, TypeScript, Tailwind CSS
2. 🔄 **Core Website Structure** - Layout components and navigation
3. 📋 **Content Sections** - About, Skills, Projects, Contact
4. 📧 **Contact Form & Backend** - Form integration and validation
5. 🎨 **Styling & Polish** - Animations and responsive design
6. ☁️ **AWS Infrastructure** - S3, CloudFront, Route 53
7. 🔄 **CI/CD Pipeline** - GitHub Actions automation
8. 🧪 **Testing & Optimization** - Performance and accessibility
9. 📝 **Content & Launch Prep** - Content creation and SEO
10. 🚀 **Launch & Post-Launch** - Deployment and monitoring

## 📋 Current Status

- ✅ Project initialized with Vite React TypeScript
- ✅ SWC configured for fast compilation
- ✅ Tailwind CSS setup with dark theme
- ✅ Basic portfolio structure implemented
- 🔄 Component structure and layout components (in progress)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Contact

- **Website**: [webbpulse.com](https://webbpulse.com) (coming soon)
- **Email**: [your-email@example.com]
- **LinkedIn**: [Your LinkedIn Profile]

---

Built with ❤️ using React, TypeScript, and Tailwind CSS
