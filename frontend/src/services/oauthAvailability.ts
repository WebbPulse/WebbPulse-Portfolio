/**
 * Which OAuth providers this deployment actually has configured.
 *
 * ## Why this is a probe rather than a read
 *
 * There is no discovery endpoint. webbpulse-python 0.14.0 mounts the five
 * OAuth routes only when `OAuthService.enabled_providers()` is non-empty, and
 * `enabled_providers` is the intersection of `oauth_providers` in settings and
 * the providers that were actually given a client id. A provider that is
 * listed but has no client id is not enabled, and a deployment with neither
 * configured has no OAuth routes in its OpenAPI document at all. None of that
 * is published anywhere the frontend can read: the only observable difference
 * between "Google is configured" and "Google is not" is what
 * `GET /api/auth/oauth/google/start` answers.
 *
 * So this probes the start route and reads the answer:
 *
 * - a redirect to the provider, or an opaque response standing in for one,
 *   means the provider is configured
 * - a 404 means the route is not mounted, which is the whole-surface case
 * - a 400 or a 503 carrying `OAUTH_PROVIDER_UNKNOWN` or
 *   `OAUTH_PROVIDER_UNAVAILABLE` means the routes exist but this provider does
 *   not, which is the per-provider case
 *
 * A discovery endpoint in the identity package would be cleaner than any of
 * this. See the note in the PR: a route answering
 * `{ providers: ['google'] }` would replace the whole file with one fetch, and
 * would let the login page render its buttons on the first paint instead of
 * after a round trip per provider.
 *
 * ## The probe cannot be an ordinary fetch
 *
 * The start route answers `302` to the provider's authorization endpoint,
 * which is a cross-origin redirect to a host that sends no CORS headers. A
 * `fetch` in the default `follow` mode would chase it and reject on the CORS
 * failure at the *provider*, which is indistinguishable from the network being
 * down. `redirect: 'manual'` is what stops that: the browser returns an opaque
 * filtered response with `type: 'opaqueredirect'` and `status: 0` rather than
 * following, so the redirect itself is the signal and nothing leaves for
 * Google or GitHub.
 *
 * The request is deliberately **not** credentialed and deliberately does not
 * consume a `mode=link` start. It burns one of the twenty starts per fifteen
 * minutes the standard's section 5.1 allows per IP, which is why the result is
 * cached for the life of the page: a login screen that re-probed on every
 * render would exhaust that bucket before a user finished typing a password.
 */
import { GITHUB_PROVIDER, GOOGLE_PROVIDER } from '@webbpulse/auth';

import { type Availability, cachedAvailability } from './availabilityCache';

export { resetAvailabilityCache } from './availabilityCache';

/**
 * The providers this application offers, in the order the buttons render.
 *
 * Google first because it is the one most users have. The names come from the
 * package's constants rather than string literals so a rename in the identity
 * standard is a compile error here rather than a button that silently 404s.
 */
export const OAUTH_PROVIDERS: readonly string[] = [
  GOOGLE_PROVIDER,
  GITHUB_PROVIDER,
];

/** A human name for a provider, for button and list copy. */
export function providerLabel(provider: string): string {
  switch (provider) {
    case GOOGLE_PROVIDER:
      return 'Google';
    case GITHUB_PROVIDER:
      return 'GitHub';
    default:
      // A provider this build does not know about, which the server can have
      // and the package explicitly allows. Title case is better than nothing
      // and better than rendering a raw lowercase wire value.
      return provider.charAt(0).toUpperCase() + provider.slice(1);
  }
}

/**
 * What one probe concluded.
 *
 * An alias of the shared {@link Availability}, kept under its old name so the
 * existing callers and tests read the same. `unknown` is not "unavailable": it
 * is what a network failure or a CORS surprise leaves behind, and the caller
 * renders nothing rather than telling a user a provider is off when the probe
 * simply could not be made.
 */
export type ProviderAvailability = Availability;

/**
 * Error codes that mean "the routes are mounted, this provider is not".
 *
 * Both are deployment facts rather than user errors, and `oauth.ts` in the
 * package folds them into one `provider-unavailable` outcome for the same
 * reason: a user can do nothing about either.
 */
const UNAVAILABLE_CODES: ReadonlySet<string> = new Set([
  'OAUTH_PROVIDER_UNKNOWN',
  'OAUTH_PROVIDER_UNAVAILABLE',
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
 * Probes one provider's start route.
 *
 * Exported for the test, which drives it against a stubbed `fetch` rather than
 * going through the cache: the cache is the thing that makes a second call
 * unobservable, and a test of the classification needs each case to actually
 * run.
 */
export async function probeProvider(
  startUrl: string,
  fetchImpl: typeof fetch = fetch
): Promise<ProviderAvailability> {
  let response: Response;
  try {
    response = await fetchImpl(startUrl, {
      method: 'GET',
      // See the file note: without this the browser follows the 302 to the
      // provider and the CORS failure there swallows the answer.
      redirect: 'manual',
      // No cookies. A start is anonymous in `login` mode, and sending the
      // refresh cookie to a route that does not read it is a habit worth not
      // forming.
      credentials: 'omit',
      headers: { accept: 'application/json' },
    });
  } catch {
    // A network failure, or the request being blocked. Nothing was learned.
    return 'unknown';
  }

  // `opaqueredirect` is what `redirect: 'manual'` produces for a cross-origin
  // 302 and it carries status 0 and no readable headers. It is the ordinary
  // success case for a configured provider, not an error.
  if (response.type === 'opaqueredirect') {
    return 'available';
  }
  if (response.status >= 300 && response.status < 400) {
    return 'available';
  }
  if (response.status === 404) {
    // The route is not mounted, so no provider is configured on this backend.
    return 'unavailable';
  }
  if (response.status === 400 || response.status === 503) {
    // The routes exist and this provider does not. The envelope says which,
    // and a 400 that is not one of those two codes is some other refusal that
    // this probe should not read as "unavailable".
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
    // so a user who reloaded a few times is not told the provider is gone.
    return 'unknown';
  }
  return 'unknown';
}

/**
 * Whether a provider is configured, probing at most once per page load.
 *
 * The cache is `services/availabilityCache.ts`, shared with the passkey probe
 * so both capability gates spend one request per page load rather than one per
 * render. See that file for why promises rather than results are stored and
 * why an `unknown` answer is not kept.
 */
export function providerAvailability(
  startUrl: string,
  fetchImpl: typeof fetch = fetch
): Promise<ProviderAvailability> {
  return cachedAvailability(startUrl, () => probeProvider(startUrl, fetchImpl));
}
