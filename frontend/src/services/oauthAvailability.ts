/**
 * Which OAuth providers this deployment actually has configured.
 *
 * ## One fetch of an explicit list, replacing a probe per provider
 *
 * webbpulse-python 0.16.0 added `GET /api/auth/oauth/providers`, and this file
 * is what it exists for. Until that release there was no discovery endpoint:
 * the only observable difference between "Google is configured" and "Google is
 * not" was what `GET /api/auth/oauth/{provider}/start` answered, so this file
 * probed the start route once per provider per page load and classified the
 * status code. That was wrong twice over.
 *
 * It spent the wrong budget. A start is rate limited to twenty per fifteen
 * minutes per IP, because a start writes a state row and an unlimited one is a
 * way to fill the table. Spending those on page loads meant a user who
 * reloaded a sign-in page enough times was refused the sign-in they then
 * attempted, which is a rate limit doing the opposite of its job.
 *
 * And it could not tell two different things apart. "This provider is not
 * configured" and "this provider is configured and something is briefly
 * broken" are both a non-200, so a blip anywhere in the start path hid a
 * working sign-in method for the life of the page.
 *
 * The discovery route answers the question directly instead. It is mounted in
 * every deployment, including one with no OAuth at all, which is what makes
 * `{"providers": []}` a real answer rather than an inference from a 404: a
 * missing route would be indistinguishable from a routing mistake or from this
 * bundle talking to a backend older than 0.16.0. It is anonymous, it is not
 * rate limited, it touches no store, and it carries
 * `Cache-Control: public, max-age=300` so repeat loads mostly do not reach the
 * function at all.
 *
 * It is also stricter than the probe could be. A provider appears only when it
 * has **both** a client id and a client secret, so the half-configured state
 * that used to send a user to a provider and meet them with a 503 on the way
 * back is now simply a provider that is never offered.
 *
 * ## Why this is not a call on `@webbpulse/auth`
 *
 * `@webbpulse/auth` 0.8.0 is the installed version and it predates the route,
 * so it has no method for it: `oauthStartUrl`, `startOAuth`, `linkOAuth` and
 * the links call are the whole OAuth surface it exposes. Rather than pin a
 * package version that does not exist yet, this fetches the route directly,
 * the same way `passkeyAvailability.ts` calls the login options route. The
 * identity origin is passed in by the caller, which is what keeps this file
 * from having to know how `API_BASE_URL` becomes an identity origin.
 *
 * When a release of the package does expose it, this file becomes a call
 * through the client and the shape below is what it has to keep answering.
 */
import { type Availability, cachedAvailability } from './availabilityCache';

export { resetAvailabilityCache } from './availabilityCache';

/** Where the discovery route lives, relative to the identity origin. */
export const OAUTH_PROVIDERS_PATH = '/api/auth/oauth/providers';

/**
 * One provider the backend says it can sign a user in with.
 *
 * Mirrors the wire shape exactly, snake case and all, so there is no mapping
 * step that could quietly drop a field. `display_name` is the backend's own
 * name for the provider and is what a button is labelled with, which is what
 * lets a provider added in a future package release render correctly here with
 * no frontend change at all.
 */
export interface OAuthProvider {
  /** The provider id, `google` or `github` today. */
  readonly id: string;
  /** The name to show a user, `Google` or `GitHub` today. */
  readonly display_name: string;
}

/**
 * A human name for a provider id, for copy that has only the id.
 *
 * Still here, and still needed, but for a smaller job than before. The
 * discovery route carries a `display_name` for every provider it offers, so a
 * sign-in button never reaches this. What does reach it is the list of
 * accounts already linked to the user, which comes from
 * `GET /api/auth/oauth/links` and carries provider ids and no display names.
 */
export function providerLabel(provider: string): string {
  switch (provider) {
    case 'google':
      return 'Google';
    case 'github':
      return 'GitHub';
    default:
      // A provider this build does not know about, which the server can have
      // and the package explicitly allows. Title case is better than nothing
      // and better than rendering a raw lowercase wire value.
      return provider.charAt(0).toUpperCase() + provider.slice(1);
  }
}

/**
 * What one availability question concluded.
 *
 * An alias of the shared {@link Availability}, kept under its old name so the
 * existing callers and tests read the same.
 */
export type ProviderAvailability = Availability;

/** Whether a parsed value is one usable provider entry. */
function isProvider(value: unknown): value is OAuthProvider {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const { id, display_name: displayName } = value as Record<string, unknown>;
  return (
    typeof id === 'string' &&
    id !== '' &&
    typeof displayName === 'string' &&
    displayName !== ''
  );
}

/**
 * Reads the provider list off a parsed body, tolerating any shape.
 *
 * Returns `undefined` for a body that is not the documented envelope, which
 * the caller turns into "nothing was learned" rather than "no providers". The
 * distinction matters: a proxy that answered 200 with an HTML error page must
 * not read as a deployment with OAuth switched off.
 *
 * Entries that are not well formed are dropped individually rather than
 * failing the whole list, so one malformed record cannot hide a provider that
 * is described correctly.
 */
function providersOf(body: unknown): OAuthProvider[] | undefined {
  if (typeof body !== 'object' || body === null) {
    return undefined;
  }
  const { providers } = body as { providers?: unknown };
  if (!Array.isArray(providers)) {
    return undefined;
  }
  return providers.filter(isProvider);
}

/**
 * Fetches the discovery route and returns what it offers.
 *
 * Exported for the test, which drives it against a stubbed `fetch` rather than
 * going through the cache: the cache is the thing that makes a second call
 * unobservable, and a test of the parsing needs each case to actually run.
 *
 * Returns `undefined` rather than `[]` for anything that is not a readable
 * answer, and the two mean different things. `[]` is the backend saying it has
 * no providers, which is a fact about the deployment and is kept for the life
 * of the page. `undefined` is a network failure, a non-200, or a body that is
 * not the envelope, which teaches nothing and is not cached.
 */
export async function fetchOAuthProviders(
  providersUrl: string,
  fetchImpl: typeof fetch = fetch
): Promise<OAuthProvider[] | undefined> {
  let response: Response;
  try {
    response = await fetchImpl(providersUrl, {
      method: 'GET',
      // Anonymous. The sign-in page has no session by definition, and the
      // route reads nothing off one.
      credentials: 'omit',
      headers: { accept: 'application/json' },
    });
  } catch {
    // A network failure, or the request being blocked. Nothing was learned.
    return undefined;
  }

  if (response.status !== 200) {
    // Including a 404, which now means something worth not guessing about: the
    // backend is older than 0.16.0. Hiding the buttons is the right outcome
    // there, but it is reached by there being nothing to render rather than by
    // reading a 404 as an empty list.
    return undefined;
  }

  try {
    return providersOf(await response.json());
  } catch {
    return undefined;
  }
}

/**
 * The providers this deployment offers, fetched at most once per page load.
 *
 * The cache is `services/availabilityCache.ts`, shared with the passkey probe
 * so both capability gates spend one request per page load rather than one per
 * render. See that file for why promises rather than results are stored and
 * why an `unknown` answer is not kept.
 *
 * The cache stores an {@link Availability}, which is a three-state string and
 * not a list, so the list itself is held alongside it in `resolved` and keyed
 * by the same URL. That keeps one cache and one eviction rule rather than two:
 * `available` and `unavailable` are both real answers and both stay, `unknown`
 * is evicted as it resolves and the next caller asks again.
 */
const resolved = new Map<string, OAuthProvider[]>();

/**
 * Empties the provider list cache. For tests only.
 *
 * `resetAvailabilityCache` re-exported above clears the shared promise cache;
 * this clears the list that sits beside it. `oauthAvailability.test.ts` and any
 * component test that renders a sign-in page call both.
 */
export function resetProviderCache(): void {
  resolved.clear();
}

/**
 * The providers to draw buttons for, in the order the backend listed them.
 *
 * The order is the backend's and is deliberately not re-sorted here. It is
 * `IdentitySettings.oauth_providers` order, which is a deployment's own
 * statement of which sign-in method it would rather a user reached for.
 *
 * Returns `[]` both for a deployment that offers none and for a question that
 * could not be answered. A caller renders nothing in either case, which is the
 * same behaviour the probe gate had: never show a button that cannot work.
 */
export async function oauthProviders(
  identityOrigin: string,
  fetchImpl: typeof fetch = fetch
): Promise<OAuthProvider[]> {
  const url = `${identityOrigin}${OAUTH_PROVIDERS_PATH}`;

  await cachedAvailability(url, async () => {
    const providers = await fetchOAuthProviders(url, fetchImpl);
    if (providers === undefined) {
      return 'unknown';
    }
    resolved.set(url, providers);
    return providers.length > 0 ? 'available' : 'unavailable';
  });

  return resolved.get(url) ?? [];
}
