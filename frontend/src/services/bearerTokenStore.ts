/**
 * The bearer token store for the pre-identity login flow.
 *
 * Local to this application and deleted at the identity cutover. A `localStorage`
 * that throws degrades to an in-memory copy, so Safari private mode cannot break
 * the application on load.
 */
export class BearerTokenStore {
  private readonly key: string;

  /** Set once `localStorage` has thrown, after which this is the only copy. */
  private fallback: string | null = null;
  private useFallback = false;

  constructor(key: string) {
    this.key = key;
  }

  /** The stored token, or null when there is none. */
  get(): string | null {
    if (this.useFallback) {
      return this.fallback;
    }
    try {
      return globalThis.localStorage.getItem(this.key);
    } catch {
      this.useFallback = true;
      return this.fallback;
    }
  }

  /** Stores a token. */
  set(token: string): void {
    this.fallback = token;
    if (this.useFallback) {
      return;
    }
    try {
      globalThis.localStorage.setItem(this.key, token);
    } catch {
      this.useFallback = true;
    }
  }

  /** Clears the token. */
  clear(): void {
    this.fallback = null;
    if (this.useFallback) {
      return;
    }
    try {
      globalThis.localStorage.removeItem(this.key);
    } catch {
      this.useFallback = true;
    }
  }
}
