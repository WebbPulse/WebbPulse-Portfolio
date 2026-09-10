/**
 * Whether this deployment offers passwordless passkey sign-in.
 *
 * ## Why this is a probe, like the OAuth one
 *
 * Same shape of problem as `services/oauthAvailability.ts`, for the same
 * reason: there is no discovery endpoint. The identity service mounts the
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
 * dance. What it does cost is one of the thirty login-options calls per
 * fifteen minutes the standard's section 5.1 allows per IP, and it consumes a
 * challenge row that is then never spent. That is why the result goes through
 * the shared once-per-page cache rather than being asked on every render.
 *
 * The body is deliberately empty rather than carrying an email. An address
 * would be a discoverable-credential request for a specific account, and the
 * probe has no account in hand: it is asking about the deployment, not about a
 * user. The server answers an empty body with a discoverable challenge, which
 * is exactly the "is this switched on" signal wanted here.
 *
 * A discovery endpoint in the identity package would replace this file and
 * `oauthAvailability.ts` both. The note in the OAuth PR still stands.
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
  return cachedAvailability(optionsUrl, () =>
    probePasskeyLogin(optionsUrl, fetchImpl)
  );
}
