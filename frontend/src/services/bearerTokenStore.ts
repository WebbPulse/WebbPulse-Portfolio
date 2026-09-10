/**
 * The bearer token store for the pre-identity login flow.
 *
 * This used to be `TokenStore` from `@webbpulse/auth`. Version 0.4.0 removed it
 * along with `TokenStorage`, `MemoryTokenStorage` and `defaultTokenStorage`,
 * and removed rather than deprecated them on purpose: section 7.1 of the
 * identity standard replaces a `localStorage` backed access token with a token
 * held in memory and an httpOnly refresh cookie, and leaving the store exported
 * invites exactly the use the design exists to stop.
 *
 * Portfolio still needs one, because its backend has not moved yet. The only
 * login route this application has is `POST /api/v1/admin/login`, which answers
 * with a bearer token in the body and sets no refresh cookie, so there is
 * nothing for `AuthClient` to silently refresh against and a token that lived
 * only in memory would be lost on every page reload. The store is therefore
 * local rather than shared: it is this application's transitional state, not a
 * pattern for other consumers to pick up, and it is deleted rather than
 * upgraded when the identity routes land. See `IDENTITY_CUTOVER` in
 * `services/api.ts`.
 *
 * Behaviour matches the store it replaces, including the one property worth
 * keeping: a `localStorage` that throws degrades to an in memory copy rather
 * than propagating. Safari in private mode throws on write, and a failed token
 * write must not take the whole application down on load.
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
