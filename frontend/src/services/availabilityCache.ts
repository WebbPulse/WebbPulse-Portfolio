/**
 * The one-probe-per-page-load cache both capability probes share.
 *
 * ## Why there is a cache at all
 *
 * webbpulse-python publishes no discovery document. Whether a deployment has
 * OAuth configured, and whether it has passwordless passkey sign-in switched
 * on, are both observable only by asking the route and reading the answer. A
 * probe is therefore a real request against a real rate limit bucket: the
 * standard's section 5.1 allows twenty OAuth starts per fifteen minutes per IP
 * and thirty passkey login options in the same window. A login screen that
 * re-probed on every render would exhaust either before a user finished typing
 * a password.
 *
 * ## Why promises are cached rather than results
 *
 * Two components mounting in the same tick is the ordinary case, not the edge
 * one: the login form and its passkey button both ask on first paint. Caching
 * the in-flight promise makes the second ask join the first request instead of
 * racing it, which is the difference between one probe and two.
 *
 * ## Why `unknown` is not cached
 *
 * A probe that failed on a flaky network learned nothing. Caching that answer
 * would hide the affordance for the life of the page over one dropped request,
 * so an `unknown` result is evicted as it resolves and the next ask probes
 * again. `unavailable` is a deployment fact and does not change under the
 * page, so it is kept.
 *
 * ## Why a second tier in `sessionStorage`
 *
 * The in-memory map above dies with the page, and a sign-in page is reloaded:
 * a failed password, a back button, a link followed and returned from. Each of
 * those was a fresh probe, so the passkey gate spent one of its thirty login
 * options calls per fifteen minutes, and one challenge row, per *reload*
 * rather than per session. A user who reloaded enough times was refused the
 * sign-in they were reloading in order to attempt.
 *
 * `sessionStorage` is the right lifetime for the answer being stored. What a
 * probe learns is a fact about the deployment, not about the user, and a
 * deployment does not switch a capability on and off inside one tab's
 * lifetime. It is scoped per tab and cleared when the tab closes, so a
 * redeploy is picked up by the next new tab rather than being remembered
 * indefinitely the way `localStorage` would.
 *
 * Only definite answers are written. `unknown` is not a fact and never reaches
 * storage, so a probe that failed once does not silence the affordance for the
 * rest of the session.
 *
 * Every read and write is wrapped, because `sessionStorage` is not merely
 * possibly empty: the accessor itself throws in a browser configured to block
 * site data, and in that case the in-memory tier alone still gives the
 * once-per-page-load behaviour this file had before.
 *
 * ## Why the session tier is opt-in rather than the default
 *
 * It is on for the passkey probe and off for the OAuth list, and the asymmetry
 * is not about caution. This cache stores a three-state string and nothing
 * else, so a caller whose real answer is richer than that string keeps the
 * rest beside it: `oauthAvailability.ts` holds the provider list in a map that
 * lives and dies with the page. Serving `available` out of storage would skip
 * the fetch that fills that map, and the sign-in page would conclude it has
 * OAuth and then render no buttons.
 *
 * The passkey gate has no such companion state. `available` is the entire
 * answer, so it survives a reload intact.
 *
 * The costs point the same way. The OAuth route is anonymous, unmetered,
 * touches no store and carries its own `Cache-Control`, so a repeat fetch is
 * usually served by the HTTP cache and is cheap when it is not. The passkey
 * probe is a rate limited POST that writes a challenge row. Only the second
 * one is worth persisting, and only the second one can be.
 */

/**
 * What one probe concluded.
 *
 * `unknown` is deliberately not `unavailable`: it is what a network failure or
 * a CORS surprise leaves behind, and a caller renders nothing rather than
 * telling a user a capability is off when the probe simply could not be made.
 */
export type Availability = 'available' | 'unavailable' | 'unknown';

/**
 * Keyed by the full probed URL, which folds the API origin into the key: two
 * bundles pointed at different backends cannot share an answer.
 */
const cache = new Map<string, Promise<Availability>>();

/**
 * Prefix for the `sessionStorage` keys, so an entry is recognisable in a
 * devtools inspector and cannot collide with anything else the app stores.
 */
const STORAGE_PREFIX = 'wp:availability:';

/** The stored key for one probed URL. */
function storageKey(key: string): string {
  return `${STORAGE_PREFIX}${key}`;
}

/**
 * The session's stored answer for a key, or `undefined`.
 *
 * Anything that is not one of the two definite answers is treated as absent,
 * which covers a stored `unknown` from some future writer as well as a value
 * corrupted by hand. The whole body is wrapped because reading the accessor
 * throws outright when a browser is set to block site data.
 */
function storedAvailability(key: string): Availability | undefined {
  try {
    const raw = globalThis.sessionStorage.getItem(storageKey(key));
    return raw === 'available' || raw === 'unavailable' ? raw : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Remembers a definite answer for the rest of the tab's session.
 *
 * `unknown` is refused rather than stored: see the file note. A write that
 * throws, which is what a full or blocked store does, leaves the in-memory
 * tier to carry the answer for this page load.
 */
function storeAvailability(key: string, result: Availability): void {
  if (result === 'unknown') {
    return;
  }
  try {
    globalThis.sessionStorage.setItem(storageKey(key), result);
  } catch {
    // Storage is unavailable or full. The memory cache still holds the answer.
  }
}

/**
 * Empties the in-memory tier only, leaving the session tier intact.
 *
 * For tests only, and it exists because this is exactly what a page load does:
 * the map above is new and `sessionStorage` is not. A test of the "does a
 * reload probe again" behaviour has no other way to produce that state, since
 * it cannot actually reload the document.
 */
export function clearAvailabilityMemoryCache(): void {
  cache.clear();
}

/**
 * Empties both tiers of the cache. For tests only.
 *
 * Clears the whole `sessionStorage` prefix rather than one key, so a test does
 * not have to know which URLs a previous test probed. Wrapped for the same
 * reason every other access here is.
 */
export function resetAvailabilityCache(): void {
  cache.clear();
  try {
    const store = globalThis.sessionStorage;
    const keys: string[] = [];
    for (let index = 0; index < store.length; index += 1) {
      const key = store.key(index);
      if (key !== null && key.startsWith(STORAGE_PREFIX)) {
        keys.push(key);
      }
    }
    for (const key of keys) {
      store.removeItem(key);
    }
  } catch {
    // Nothing stored, nothing to clear.
  }
}

/**
 * Runs `probe` at most once per key per page load, and with `persist` at most
 * once per key per tab session.
 *
 * See the file note for why the promise rather than the result is stored, why
 * an `unknown` answer is evicted, and why a definite answer outlives the page.
 *
 * @param persist - Whether a definite answer is remembered in `sessionStorage`
 * and reused across reloads. Pass it for a probe that costs a rate limit
 * budget or a stored row, and only when the three-state answer is the whole
 * answer: a caller holding companion state beside the cache must leave this
 * off, or a reload serves the verdict without the state that goes with it.
 */
export function cachedAvailability(
  key: string,
  probe: () => Promise<Availability>,
  { persist = false }: { persist?: boolean } = {}
): Promise<Availability> {
  const cached = cache.get(key);
  if (cached !== undefined) {
    return cached;
  }

  // A definite answer this session already paid for. Promoted into the memory
  // tier so the rest of this page load is served without touching storage
  // again, and so a caller that inspects the cache sees one story.
  const stored = persist ? storedAvailability(key) : undefined;
  if (stored !== undefined) {
    const resolved = Promise.resolve(stored);
    cache.set(key, resolved);
    return resolved;
  }

  const pending = probe().then(result => {
    if (result === 'unknown') {
      cache.delete(key);
    } else if (persist) {
      storeAvailability(key, result);
    }
    return result;
  });
  cache.set(key, pending);
  return pending;
}
