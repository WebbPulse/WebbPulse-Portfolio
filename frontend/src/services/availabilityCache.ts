/**
 * The one-fetch-per-page-load cache both capability gates share.
 *
 * Caches the in-flight promise so simultaneous askers join one request, and
 * keeps the answer stable across a render.
 */

/**
 * What one availability question concluded.
 *
 * `unknown` is not `unavailable`: it is what a failed request leaves behind, and
 * a caller renders nothing rather than claiming a capability is off.
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
