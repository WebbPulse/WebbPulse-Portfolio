import { useSyncExternalStore } from 'react';

/** A subscription that never fires, for values that do not change. */
const noSubscription = () => () => {};

/**
 * A value only the browser can know, read after hydration.
 *
 * The prerender and the hydrating render both see `serverValue`, so the markup
 * matches; React then re-renders with `read()` on the client.
 */
export function useClientValue<T>(read: () => T, serverValue: T): T {
  return useSyncExternalStore(noSubscription, read, () => serverValue);
}
