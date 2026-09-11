/**
 * Which auth mechanism this bundle uses.
 *
 * Two mechanisms exist in the estate and Portfolio is between them.
 *
 * `bearer` is what ships today. `POST /api/v1/admin/login` answers with a
 * bearer token in the body, the token goes to `BearerTokenStore`, and every
 * request carries it through the client's `getAuthToken`. There is no refresh
 * endpoint and no refresh cookie, so a token lives until it expires and the
 * user signs in again.
 *
 * `identity` is the unified identity standard of sections 7.1 to 7.3, which
 * `@webbpulse/auth` 0.4.0 implements as `AuthClient`: a short lived access
 * token held in memory, an httpOnly refresh cookie the page cannot read, one
 * shared in-flight refresh, and a retry-once-on-401 pipeline turned on by
 * passing the client as `auth`.
 *
 * The switch is configuration rather than a branch waiting on a rewrite. The
 * `identity` path is written and typed against the real 0.4.0 API, so turning
 * it on is a deploy time decision and not a code change. What it is waiting on
 * is the backend: Portfolio staging serves `/api/auth/.well-known/jwks.json`,
 * `/api/auth/.well-known/openid-configuration` and `/api/auth/health` from the
 * identity function, and nothing else. `AuthClient` needs `/api/auth/login`,
 * `/api/auth/refresh` and `/api/auth/logout`, none of which exist yet, so
 * setting this to `identity` today would break signing in. It is set when those
 * routes are live, and the bearer path and its store are deleted after.
 *
 * Read through `@webbpulse/config`'s `ConfigReader` rather than
 * `import.meta.env` directly, so an unparseable value is a named startup
 * failure alongside every other configuration problem instead of a silent
 * falsey read.
 */
export const AUTH_MODES = ['bearer', 'identity'] as const;

/** One of {@link AUTH_MODES}. */
export type AuthMode = (typeof AUTH_MODES)[number];

/**
 * The env var that selects the mechanism. Absent means `bearer`.
 *
 * Named for what it selects rather than for a flag, because it outlives the
 * migration only as the value `identity` and then goes away entirely.
 */
export const AUTH_MODE_ENV_KEY = 'VITE_AUTH_MODE';
