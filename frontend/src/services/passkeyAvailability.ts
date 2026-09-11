/**
 * Whether this deployment offers passwordless passkey sign-in.
 *
 * ## Why this is still a probe when the OAuth one no longer is
 *
 * webbpulse-python 0.16.0 replaced the OAuth probe with
 * `GET /api/auth/oauth/providers`, and the obvious move was to do the same
 * here. There is nothing to move to. 0.16.0 adds exactly one discovery route
 * and it is about OAuth: it answers a provider list and carries no passkey
 * field. The OIDC discovery document at
 * `/api/auth/.well-known/openid-configuration` is not a candidate either. It
 * is `build_discovery_document`, a pure function of the issuer returning five
 * fixed keys, `issuer`, `jwks_uri`, `response_types_supported`,
 * `subject_types_supported` and `id_token_signing_alg_values_supported`, none
 * of which says anything about a capability. And there is no
 * `/api/auth/passkeys/config` route: the only passkey GET the package mounts
 * is `GET /api/auth/passkeys`, which lists the signed-in user's own
 * credentials from behind the authorizer, so it is useless to a sign-in page
 * that by definition holds no token.
 *
 * **A package change would settle this.** A future release adding
 * `GET /api/auth/passkeys/availability`, unconditional and anonymous and
 * `Cache-Control`ed the way `oauth/providers` is, would delete this probe
 * outright and turn this file into one fetch and one field read.
 *
 * Until then: the identity service mounts the
 * passkey routes only when the capability is configured, and it can mount the
 * enrolment routes while leaving passwordless sign-in off. Neither fact is
 * published anywhere the bundle can read. The only observable difference
 * between "passkey sign-in works here" and "it does not" is what
 * `POST /api/auth/login/passkey/options` answers.
 *
 * So this probes that route and reads the answer:
 *
 * - a 200 carrying a challenge means passwordless sign-in is on
 * - a 404 means the route is not mounted at all, which is the whole-surface
 *   case and the one the brief calls out
 * - a 4xx or 503 carrying `PASSKEYS_DISABLED` or `PASSKEY_LOGIN_DISABLED`
 *   means the routes exist and this capability does not
 *
 * ## Why this probe is cheaper than it looks
 *
 * Unlike the OAuth start route, this one is an ordinary same-origin JSON POST:
 * no redirect to a third party, no CORS surprise, no `redirect: 'manual'`
 * dance. What it does cost is real: one of the thirty login-options calls per
 * fifteen minutes that `PASSKEY_OPTIONS_LIMIT` allows per IP, and a challenge
 * row that is written and then never spent.
 *
 * So the answer is cached for the tab's session rather than for the page load.
 * A page-load cache still meant a probe per *reload*, and a sign-in page is
 * reloaded: a mistyped password, a back button, a link followed and returned
 * from. Thirty of those in a quarter of an hour is not a hostile number, and
 * hitting it meant the rate limiter refusing the sign-in the user was
 * reloading in order to attempt. The verdict is a fact about the deployment,
 * not about the user, so it is the same on the next reload and there is
 * nothing to learn by asking again.
 *
 * The probe is also gated on `passkeysSupported()` in `usePasskeySignIn`,
 * which reads `PublicKeyCredential` off the global. A browser that cannot do
 * WebAuthn never reaches this file at all, so it never spends a request
 * finding out about a capability it could not use.
 *
 * The body is deliberately empty rather than carrying an email. An address
 * would be a discoverable-credential request for a specific account, and the
 * probe has no account in hand: it is asking about the deployment, not about a
 * user. The server answers an empty body with a discoverable challenge, which
 * is exactly the "is this switched on" signal wanted here.
 */
import { type Availability, cachedAvailability } from './availabilityCache';

/** Where the login options route lives, relative to the identity origin. */
export const PASSKEY_LOGIN_OPTIONS_PATH = '/api/auth/login/passkey/options';

/**
 * Error codes that mean "the identity service is there, passkey sign-in is
 * not".
 *
 * `PASSKEYS_DISABLED` is the capability off altogether and
 * `PASSKEY_LOGIN_DISABLED` is passwordless sign-in specifically off while
 * enrolment still works. The package folds both into one `unavailable`
 * outcome, and this gate does the same: a user can do nothing about either,
 * and the button is hidden in both cases.
 */
const UNAVAILABLE_CODES: ReadonlySet<string> = new Set([
  'PASSKEYS_DISABLED',
  'PASSKEY_LOGIN_DISABLED',
]);

/** Reads `error_code` off the backend's error envelope, tolerating any shape. */
function errorCodeOf(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null) {
    return undefined;
  }
  const code = (body as { error_code?: unknown }).error_code;
  return typeof code === 'string' ? code : undefined;
}

/**
 * Probes the login options route.
 *
 * Exported for the test, which drives it directly rather than through the
 * cache: the cache is the thing that makes a second call unobservable, and a
 * test of the classification needs each case to actually run.
 */
export async function probePasskeyLogin(
  optionsUrl: string,
  fetchImpl: typeof fetch = fetch
): Promise<Availability> {
  let response: Response;
  try {
    response = await fetchImpl(optionsUrl, {
      method: 'POST',
      // Anonymous. A sign-in options call has no session by definition, and
      // sending the refresh cookie to a route that does not read it is a habit
      // worth not forming.
      credentials: 'omit',
      headers: {
        accept: 'application/json',
        'content-type': 'application/json',
      },
      // No email. See the file note: the question is about the deployment.
      body: '{}',
    });
  } catch {
    // A network failure, or the request being blocked. Nothing was learned.
    return 'unknown';
  }

  if (response.status === 200) {
    return 'available';
  }
  if (response.status === 404) {
    // The route is not mounted. This is the case the brief names, and the one
    // that has to hide the button rather than render an error.
    return 'unavailable';
  }
  if (
    response.status === 400 ||
    response.status === 403 ||
    response.status === 503
  ) {
    // The identity service is there and the capability is not. The envelope
    // says which, and a refusal that is not one of those two codes is
    // something else this probe should not read as "unavailable".
    try {
      const body: unknown = await response.json();
      const code = errorCodeOf(body);
      return code !== undefined && UNAVAILABLE_CODES.has(code)
        ? 'unavailable'
        : 'unknown';
    } catch {
      return 'unknown';
    }
  }
  if (response.status === 429) {
    // Rate limited, which says nothing about configuration. Treated as unknown
    // so a user who reloaded a few times is not told the feature is gone.
    return 'unknown';
  }
  return 'unknown';
}

/**
 * Whether passwordless passkey sign-in is offered, probing at most once per
 * page load.
 *
 * Shares `services/availabilityCache.ts` with the OAuth gate, so the two
 * capability probes have one eviction rule and one story about `unknown`.
 */
export function passkeyLoginAvailability(
  optionsUrl: string,
  fetchImpl: typeof fetch = fetch
): Promise<Availability> {
  return cachedAvailability(
    optionsUrl,
    () => probePasskeyLogin(optionsUrl, fetchImpl),
    // Remembered for the tab's session, not just the page load. This is the
    // expensive probe of the two and the only one whose answer is complete on
    // its own. See `availabilityCache.ts`.
    { persist: true }
  );
}
