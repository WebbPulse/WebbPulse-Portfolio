import { describe, expect, it, vi } from 'vitest';
import {
  describeOAuthCallbackError,
  readOAuthCallback,
  stripOAuthParams,
} from '@webbpulse/auth';

const ADMIN = 'https://www.example.test/admin';

describe('the OAuth callback the admin panel lands on', () => {
  it('reads a completed sign-in', () => {
    expect(readOAuthCallback(`${ADMIN}?oauth=1`)).toEqual({
      kind: 'signed-in',
    });
  });

  it('reads an MFA ticket, which the existing TOTP screen finishes', () => {
    const result = readOAuthCallback(`${ADMIN}?mfa_ticket=tkt-123`);

    expect(result).toEqual({ kind: 'mfa-required', ticket: 'tkt-123' });
  });

  it('reads a completed link', () => {
    expect(readOAuthCallback(`${ADMIN}?oauth_linked=1`)).toEqual({
      kind: 'linked',
    });
  });

  it('reads a refusal and names the code', () => {
    const result = readOAuthCallback(`${ADMIN}?oauth_error=OAUTH_CANCELLED`);

    expect(result).toMatchObject({
      kind: 'error',
      rawCode: 'OAUTH_CANCELLED',
    });
  });

  it('returns null for a direct visit, which is every ordinary load', () => {
    expect(readOAuthCallback(ADMIN)).toBeNull();
  });

  it('lets an error outrank a stale success parameter', () => {
    const result = readOAuthCallback(
      `${ADMIN}?oauth=1&oauth_error=OAUTH_STATE_INVALID`
    );

    expect(result).toMatchObject({ kind: 'error' });
  });

  it('strips every callback parameter and keeps the rest', () => {
    const stripped = stripOAuthParams(
      `${ADMIN}?tab=security&mfa_ticket=tkt-123&oauth=1`
    );

    expect(stripped).toBe(`${ADMIN}?tab=security`);
    expect(stripped).not.toContain('tkt-123');
  });

  it('reads nothing from a URL it already stripped', () => {
    const stripped = stripOAuthParams(`${ADMIN}?oauth=1`);

    expect(readOAuthCallback(stripped)).toBeNull();
  });

  it('describes a cancellation flatly rather than as an error', () => {
    const result = readOAuthCallback(`${ADMIN}?oauth_error=OAUTH_CANCELLED`);
    if (result?.kind !== 'error') throw new Error('expected an error result');

    expect(describeOAuthCallbackError(result)).toBe('Sign-in was cancelled.');
  });

  it('describes an unknown code with the fallback', () => {
    const result = readOAuthCallback(`${ADMIN}?oauth_error=SOMETHING_NEW`);
    if (result?.kind !== 'error') throw new Error('expected an error result');

    expect(describeOAuthCallbackError(result)).toMatch(
      /could not finish signing in/i
    );
    expect(result.code).toBeUndefined();
  });
});

describe('the landing sequence the panel runs', () => {
  /**
   * The mount effect, reduced to the part worth asserting on.
   *
   * Mirrored here rather than rendering the panel, which would need every content
   * route stubbed to reach the effect.
   */
  function land(href: string, handlers: Record<string, (v?: string) => void>) {
    const result = readOAuthCallback(href);
    const cleaned = result !== null ? stripOAuthParams(href) : href;
    switch (result?.kind) {
      case 'signed-in':
        handlers['signedIn']?.();
        break;
      case 'mfa-required':
        handlers['mfa']?.(result.ticket);
        break;
      case 'linked':
        handlers['linked']?.();
        break;
      case 'error':
        handlers['error']?.(describeOAuthCallbackError(result));
        break;
    }
    return cleaned;
  }

  it('initializes the session and clears the URL on a sign-in', () => {
    const signedIn = vi.fn();

    const cleaned = land(`${ADMIN}?oauth=1`, { signedIn });

    expect(signedIn).toHaveBeenCalledOnce();
    expect(cleaned).toBe(ADMIN);
  });

  it('hands the ticket to the TOTP screen and clears it from the URL', () => {
    const mfa = vi.fn();

    const cleaned = land(`${ADMIN}?mfa_ticket=tkt-123`, { mfa });

    expect(mfa).toHaveBeenCalledWith('tkt-123');
    expect(cleaned).not.toContain('tkt-123');
  });

  it('asks for a links reload on a link callback', () => {
    const linked = vi.fn();

    land(`${ADMIN}?oauth_linked=1`, { linked });

    expect(linked).toHaveBeenCalledOnce();
  });

  it('renders a friendly message on a refusal', () => {
    const error = vi.fn();

    land(`${ADMIN}?oauth_error=OAUTH_EMAIL_UNVERIFIED`, { error });

    expect(error).toHaveBeenCalledWith(
      expect.stringMatching(/cannot confirm belongs to you/i)
    );
  });

  it('leaves an ordinary load alone', () => {
    const signedIn = vi.fn();

    const cleaned = land(ADMIN, { signedIn });

    expect(signedIn).not.toHaveBeenCalled();
    expect(cleaned).toBe(ADMIN);
  });
});
