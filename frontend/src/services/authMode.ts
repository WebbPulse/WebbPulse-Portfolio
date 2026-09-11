/**
 * Which auth mechanism this bundle uses.
 *
 * `bearer` posts to the admin login route and stores the token; `identity` uses
 * the short-lived token and refresh cookie of `@webbpulse/auth`. Configuration,
 * not a code branch, so the cutover is a deploy time decision.
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
