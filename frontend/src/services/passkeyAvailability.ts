/**
 * Whether this deployment offers passkeys, and whether they are a way in.
 *
 * ## One cached GET, replacing a probe that wrote a row
 *
 * webbpulse-python 0.17.0 added `GET /api/auth/passkeys/availability`, and
 * this file is what it exists for. It is the release the previous version of
 * this file asked for by name.
 *
 * Until it there was nothing to ask. The identity service mounts the passkey
 * routes only when the capability is configured and it can mount the enrolment
 * routes while leaving passwordless sign-in off, and neither fact was
 * published anywhere the bundle could read. `GET /api/auth/oauth/providers`
 * answers a provider list and carries no passkey field. The OIDC discovery
 * document is a pure function of the issuer returning five fixed keys, none of
 * which describes a capability. `GET /api/auth/passkeys` lists the signed-in
 * user's own credentials from behind the authorizer, so it is useless to a
 * sign-in page that by definition holds no token. So the only observable
 * difference between "passkey sign-in works here" and "it does not" was what
 * `POST /api/auth/login/passkey/options` answered, and this file probed it.
 *
 * That was wrong twice over, which is the reasoning the package's own
 * changelog gives for the route.
 *
 * It spent the wrong budget. The options route is rate limited to thirty calls
 * per fifteen minutes per IP, and spending those on sign-in *page loads*
 * rather than on sign-ins meant a user who reloaded enough times was refused
 * the passkey sign-in they were reloading in order to attempt. A rate limit
 * doing the opposite of its job.
 *
 * And the probe was not a read. `begin_passkey_login` writes a WebAuthn
 * challenge row per call, so every sign-in page load in the estate left a row
 * in the challenge table to expire: a storage cost paid to answer a question
 * about configuration.
 *
 * The discovery route answers the question directly instead. It is anonymous,
 * it is not rate limited, it touches no store, it writes nothing, and it
 * carries `Cache-Control: public, max-age=300` so repeat loads mostly do not
 * reach the function at all.
 *
 * ## Why it is trustworthy in the negative
 *
 * It mounts in **every** deployment, including one with passkeys switched off
 * and the documents-only one that supplies no passkey stores at all. That is
 * deliberate package design on the same terms as `oauth/providers`: an absent
 * route answers 404, and a 404 is indistinguishable from a routing mistake, a
 * gateway misconfiguration, or this bundle talking to a backend older than
 * 0.17.0. `{"enabled": false}` is a real answer rather than an inference.
 *
 * The other seven passkey routes do not mount when they cannot work, because a
 * route that can only answer 503 is worse than an absent one. This one can
 * always work.
 *
 * ## The two fields, and why `passwordless` can be read alone
 *
 * `enabled` says the deployment registers and verifies passkeys at all, so an
 * account settings page should offer to add one. `passwordless` says a passkey
 * is a way *into* an account, so a sign-in page should offer the button. With
 * `enabled` true and `passwordless` false a passkey is a managed credential
 * and a second factor but not an entry point, which is the distinction
 * `begin_passkey_login` already enforces and the one the old probe could see
 * only as the difference between `PASSKEYS_DISABLED` and
 * `PASSKEY_LOGIN_DISABLED`.
 *
 * The package gates `passwordless` on `enabled` inside the route, so the two
 * can never disagree on the wire and a caller that wants the sign-in button
 * can read `passwordless` alone. This file does not re-derive that gate: doing
 * so would be a second opinion about a server invariant, and if the server
 * ever broke it the right outcome is to see what the server said.
 *
 * ## Why the `sessionStorage` tier went away with the probe
 *
 * PR 182 added a persistent tier to `availabilityCache.ts` because a reload
 * cost another rate limit slot and another challenge row, and the first load
 * of every session paid both anyway. The package's changelog says as much: a
 * cache in one frontend is not a fix.
 *
 * With this route there is nothing left to protect. A reload costs at most one
 * anonymous GET of a five-minute-cacheable response holding two booleans, and
 * the browser's own HTTP cache serves most of those without a request. Keeping
 * a hand-rolled `sessionStorage` tier to save that would be storing a
 * deployment fact for longer than the deployment is guaranteed to hold it, in
 * a place no redeploy can invalidate, to avoid a fetch the platform already
 * avoids. `Cache-Control` is the same idea implemented by the browser, with
 * correct invalidation. So the tier is gone, and `availabilityCache.ts` is
 * back to the single in-memory map it was before PR 182. Nothing else used
 * `persist`: `oauthAvailability.ts` deliberately did not, for a reason that
 * file states.
 *
 * ## What still gates this, and what does not
 *
 * `usePasskeySignIn` still checks `passkeysSupported()`, which reads
 * `PublicKeyCredential` off the global, before it asks this file anything, and
 * still asks `conditionalMediationAvailable()` only after this route has said
 * yes. Those are browser capabilities and this route answers a question about
 * the server, so neither replaces the other: a browser that cannot do WebAuthn
 * must not be shown a button however the deployment is configured, and a
 * deployment with passwordless off must not be shown one however capable the
 * browser is.
 */
import { cachedAvailability } from './availabilityCache';

/** Where the availability route lives, relative to the identity origin. */
export const PASSKEY_AVAILABILITY_PATH = '/api/auth/passkeys/availability';

/**
 * What the deployment says about passkeys.
 *
 * Mirrors the wire shape, so there is no mapping step that could quietly drop
 * or invert a field.
 */
export interface PasskeyAvailability {
  /** Passkeys can be registered and verified, so a settings page can offer one. */
  readonly enabled: boolean;
  /** A passkey is a way into an account, so a sign-in page can offer the button. */
  readonly passwordless: boolean;
}

/**
 * What is assumed when the question could not be answered.
 *
 * Both false, which renders no affordance. It is the same conclusion the probe
 * gate reached from an `unknown`, and it is the only safe one: a button that
 * starts a ceremony against routes that are not mounted fails in the browser's
 * own dialog, where there is nowhere to put an explanation.
 */
const UNKNOWN: PasskeyAvailability = { enabled: false, passwordless: false };

/**
 * Reads the two booleans off a parsed body, or `undefined` for anything else.
 *
 * `undefined` means nothing was learned and is not cached, which is the
 * distinction that keeps a proxy answering 200 with an HTML error page from
 * reading as a deployment with passkeys switched off.
 *
 * Both fields are required rather than defaulted. A body carrying only
 * `enabled` is not this route's envelope, and guessing `passwordless` from a
 * response that did not state it is exactly the kind of inference this route
 * was added to remove.
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
 * Exported for the test, which drives it against a stubbed `fetch` rather than
 * going through the cache: the cache is the thing that makes a second call
 * unobservable, and a test of the parsing needs each case to actually run.
 */
export async function fetchPasskeyAvailability(
  availabilityUrl: string,
  fetchImpl: typeof fetch = fetch
): Promise<PasskeyAvailability | undefined> {
  let response: Response;
  try {
    response = await fetchImpl(availabilityUrl, {
      method: 'GET',
      // Anonymous. A sign-in page has no session by definition, and the route
      // reads nothing off one.
      credentials: 'omit',
      headers: { accept: 'application/json' },
    });
  } catch {
    // A network failure, or the request being blocked. Nothing was learned.
    return undefined;
  }

  if (response.status !== 200) {
    // Including a 404, which means something worth not guessing about: the
    // backend is older than 0.17.0. Rendering no passkey affordance is the
    // right outcome there, but it is reached by there being nothing to render
    // rather than by reading a 404 as "switched off".
    return undefined;
  }

  try {
    return availabilityOf(await response.json());
  } catch {
    return undefined;
  }
}

/**
 * The answers this deployment gave, held beside the shared availability cache.
 *
 * The cache stores a three-state string and this answer is two booleans, so
 * the pair lives here keyed by the same URL. It is the arrangement
 * `oauthAvailability.ts` uses for its provider list and it keeps one cache and
 * one eviction rule rather than two.
 */
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
 * Returns both fields, because the two callers want different ones: a sign-in
 * page reads `passwordless` and an account settings page reads `enabled`.
 * Returns both false for a question that could not be answered, which renders
 * nothing and is the same conclusion the probe gate reached from an `unknown`.
 */
export async function passkeyAvailability(
  identityOrigin: string,
  fetchImpl: typeof fetch = fetch
): Promise<PasskeyAvailability> {
  const url = `${identityOrigin}${PASSKEY_AVAILABILITY_PATH}`;

  await cachedAvailability(url, async () => {
    const answer = await fetchPasskeyAvailability(url, fetchImpl);
    if (answer === undefined) {
      // Not cached, so the next caller asks again rather than the affordance
      // being silenced for the life of the page by one blip.
      return 'unknown';
    }
    resolved.set(url, answer);
    // `available` and `unavailable` are both real answers and both stay. Which
    // one it is does not matter to any caller, since the booleans beside it
    // carry the whole answer; what matters is that it is not `unknown`.
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
