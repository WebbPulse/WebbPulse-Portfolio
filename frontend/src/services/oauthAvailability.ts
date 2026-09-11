/**
 * Which OAuth providers this deployment actually has configured.
 *
 * Reads the anonymous, cacheable discovery route, which lists a provider only
 * when it has both a client id and a client secret.
 */
import { type Availability, cachedAvailability } from './availabilityCache';

export { resetAvailabilityCache } from './availabilityCache';

/** Where the discovery route lives, relative to the identity origin. */
export const OAUTH_PROVIDERS_PATH = '/api/auth/oauth/providers';

/**
 * One provider the backend says it can sign a user in with.
 *
 * Mirrors the wire shape, so a provider added server side needs no change here.
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
 * Linked-account lists carry ids and no display names, unlike the discovery route.
 */
export function providerLabel(provider: string): string {
  switch (provider) {
    case 'google':
      return 'Google';
    case 'github':
      return 'GitHub';
    default:
      return provider.charAt(0).toUpperCase() + provider.slice(1);
  }
}

/** What one availability question concluded; an alias of {@link Availability}. */
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
 * Returns `undefined` for a body that is not the envelope, and drops malformed
 * entries individually so one bad record cannot hide the rest.
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
 * Returns `undefined` rather than `[]` when nothing was learned; `[]` is the
 * deployment saying it has no providers.
 */
export async function fetchOAuthProviders(
  providersUrl: string,
  fetchImpl: typeof fetch = fetch
): Promise<OAuthProvider[] | undefined> {
  let response: Response;
  try {
    response = await fetchImpl(providersUrl, {
      method: 'GET',
      credentials: 'omit',
      headers: { accept: 'application/json' },
    });
  } catch {
    return undefined;
  }

  if (response.status !== 200) {
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
 * The list is held beside the shared availability cache, keyed by the same URL.
 */
const resolved = new Map<string, OAuthProvider[]>();

/** Empties the provider list that sits beside the shared cache. For tests only. */
export function resetProviderCache(): void {
  resolved.clear();
}

/**
 * The providers to draw buttons for, in the order the backend listed them.
 *
 * Returns `[]` both when none are offered and when the question could not be
 * answered, so a caller never draws a button that cannot work.
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
