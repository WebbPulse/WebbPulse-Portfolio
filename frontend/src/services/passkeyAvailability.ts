/**
 * Whether this deployment offers passkeys, and whether they are a way in.
 *
 * Reads the anonymous, cacheable availability route so a sign-in page can ask
 * about the server without spending a rate limit slot or writing a challenge row.
 */
import { cachedAvailability } from './availabilityCache';

/** Where the availability route lives, relative to the identity origin. */
export const PASSKEY_AVAILABILITY_PATH = '/api/auth/passkeys/availability';

/** What the deployment says about passkeys, mirroring the wire shape. */
export interface PasskeyAvailability {
  /** Passkeys can be registered and verified, so a settings page can offer one. */
  readonly enabled: boolean;
  /** A passkey is a way into an account, so a sign-in page can offer the button. */
  readonly passwordless: boolean;
}

/** What is assumed when the question could not be answered: no affordance. */
const UNKNOWN: PasskeyAvailability = { enabled: false, passwordless: false };

/**
 * Reads the two booleans off a parsed body, or `undefined` for anything else.
 *
 * `undefined` means nothing was learned, so it is not cached.
 */
function availabilityOf(body: unknown): PasskeyAvailability | undefined {
  if (typeof body !== 'object' || body === null) {
    return undefined;
  }
  const { enabled, passwordless } = body as Record<string, unknown>;
  if (typeof enabled !== 'boolean' || typeof passwordless !== 'boolean') {
    return undefined;
  }
  return { enabled, passwordless };
}

/**
 * Fetches the availability route and returns what it says.
 *
 * Exported so the test can drive it against a stubbed fetch, past the cache.
 */
export async function fetchPasskeyAvailability(
  availabilityUrl: string,
  fetchImpl: typeof fetch = fetch
): Promise<PasskeyAvailability | undefined> {
  let response: Response;
  try {
    response = await fetchImpl(availabilityUrl, {
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
    return availabilityOf(await response.json());
  } catch {
    return undefined;
  }
}

/** The answers this deployment gave, keyed by URL beside the availability cache. */
const resolved = new Map<string, PasskeyAvailability>();

/**
 * Empties the answer map. For tests only.
 *
 * `resetAvailabilityCache` clears the shared promise cache; this clears what
 * sits beside it. A test that renders a sign-in page calls both.
 */
export function resetPasskeyAvailabilityCache(): void {
  resolved.clear();
}

/**
 * What this deployment offers, fetched at most once per page load.
 *
 * Both false when the question could not be answered, which renders nothing.
 */
export async function passkeyAvailability(
  identityOrigin: string,
  fetchImpl: typeof fetch = fetch
): Promise<PasskeyAvailability> {
  const url = `${identityOrigin}${PASSKEY_AVAILABILITY_PATH}`;

  await cachedAvailability(url, async () => {
    const answer = await fetchPasskeyAvailability(url, fetchImpl);
    if (answer === undefined) {
      return 'unknown';
    }
    resolved.set(url, answer);
    return answer.enabled ? 'available' : 'unavailable';
  });

  return resolved.get(url) ?? UNKNOWN;
}

/**
 * Whether passwordless passkey sign-in is offered here.
 *
 * The sign-in page's question, kept as its own function because that page
 * should not have to know that the answer arrives beside another field.
 */
export async function passkeyLoginOffered(
  identityOrigin: string,
  fetchImpl: typeof fetch = fetch
): Promise<boolean> {
  return (await passkeyAvailability(identityOrigin, fetchImpl)).passwordless;
}
