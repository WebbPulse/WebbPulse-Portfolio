/**
 * The one-fetch-per-page-load cache both capability gates share.
 *
 * ## Why there is a cache at all
 *
 * Neither gate probes any more. `oauthAvailability.ts` reads
 * `GET /api/auth/oauth/providers` since webbpulse-python 0.16.0 and
 * `passkeyAvailability.ts` reads `GET /api/auth/passkeys/availability` since
 * 0.17.0, and both routes are anonymous, unrated, store-free and
 * `Cache-Control: public, max-age=300`. So this cache is no longer standing
 * between a login screen and a rate limit bucket.
 *
 * It still earns its place, for the coalescing below. Two components mounting
 * in the same tick is the ordinary case rather than the edge one: the login
 * form and its passkey button both ask on first paint, and the browser's HTTP
 * cache does not merge two in-flight requests for the same URL the way this
 * does. One fetch per page load is also what keeps the answer stable across a
 * render, so a component cannot see `available` and then `unknown` without the
 * deployment having changed.
 *
 * ## Why promises are cached rather than results
 *
 * That is the coalescing. Caching the in-flight promise makes the second ask
 * join the first request instead of racing it, which is the difference between
 * one fetch and two.
 *
 * ## Why `unknown` is not cached
 *
 * A fetch that failed on a flaky network learned nothing. Caching that answer
 * would hide the affordance for the life of the page over one dropped request,
 * so an `unknown` result is evicted as it resolves and the next ask fetches
 * again. `unavailable` is a deployment fact and does not change under the
 * page, so it is kept.
 *
 * ## Why there is no `sessionStorage` tier
 *
 * There was one, added in PR 182 and removed with the passkey probe it existed
 * for. The probe cost one of thirty rate limited calls per fifteen minutes and
 * wrote a WebAuthn challenge row, so a reload was worth avoiding at the price
 * of a hand-rolled persistent cache. The route that replaced it costs an
 * anonymous GET of two booleans that the browser's own HTTP cache already
 * holds for five minutes.
 *
 * Storing a deployment fact in `sessionStorage` to save that fetch would mean
 * keeping it in a place no redeploy can invalidate, to avoid a request the
 * platform avoids already and invalidates correctly. `Cache-Control` is the
 * same idea with the right lifetime, so the tier is not merely unnecessary now
 * but worse than what replaced it.
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

/** Empties the cache. For tests only. */
export function resetAvailabilityCache(): void {
  cache.clear();
}

/**
 * Runs `probe` at most once per key per page load.
 *
 * See the file note for why the promise rather than the result is stored and
 * why an `unknown` answer is evicted.
 */
export function cachedAvailability(
  key: string,
  probe: () => Promise<Availability>
): Promise<Availability> {
  const cached = cache.get(key);
  if (cached !== undefined) {
    return cached;
  }
  const pending = probe().then(result => {
    if (result === 'unknown') {
      cache.delete(key);
    }
    return result;
  });
  cache.set(key, pending);
  return pending;
}
