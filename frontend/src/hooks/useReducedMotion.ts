import { useSyncExternalStore } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';

/** Listens for changes to the reduced motion preference. */
function subscribe(onChange: () => void): () => void {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {};
  const mq = window.matchMedia(QUERY);
  mq.addEventListener('change', onChange);
  return () => mq.removeEventListener('change', onChange);
}

/** The current reduced motion preference, false when it cannot be read. */
function read(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia(QUERY).matches;
}

/**
 * Returns true if the user has requested reduced motion via OS settings.
 * Updates live if the preference changes, and reads false while hydrating.
 */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, read, () => false);
}
