import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { PasskeySignInOutcome } from '@webbpulse/auth';

import { LoginForm } from './LoginForm';
import { apiService } from '../../services/api';
import { resetAvailabilityCache } from '../../services/availabilityCache';

// The subject here is the gate and the ceremony, not the transport.
// `@webbpulse/auth` already tests turning a response into an outcome, so the
// client is stubbed and what is pinned down is the three questions that have
// to all answer yes before a button appears, and what the form does with each
// outcome the ceremony can produce.
//
// jsdom has no `PublicKeyCredential`, which is exactly what `passkeysSupported`
// reads, so the unsupported case is the default and support is stubbed in.

/** Puts a `PublicKeyCredential` on the global, as a real browser has. */
function supportWebAuthn(conditional = false): void {
  vi.stubGlobal('PublicKeyCredential', {
    isConditionalMediationAvailable: () => Promise.resolve(conditional),
  });
}

/**
 * A fetch that answers the login options probe with `status`.
 *
 * The OAuth gate probes through the same global on this page, so every helper
 * that counts calls filters by URL rather than by total: two of the calls in
 * any render belong to `useOAuthProviders` and say nothing about passkeys.
 */
function probeFetch(status: number, body: unknown = { challenge_id: 'c1' }) {
  return vi.fn().mockResolvedValue(
    new Response(status === 404 ? null : JSON.stringify(body), {
      status,
      ...(status === 404
        ? {}
        : { headers: { 'content-type': 'application/json' } }),
    })
  );
}

/** How many times the passkey login options route was asked. */
function passkeyProbeCount(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter(call =>
    String(call[0]).includes('/api/auth/login/passkey/options')
  ).length;
}

/** The slice of `AuthClient` this form touches. */
function stubIdentity(overrides: Record<string, unknown> = {}) {
  return {
    requestPasswordReset: vi.fn(),
    oauthStartUrl: (provider: string) => `https://api.test/oauth/${provider}`,
    signInWithPasskey: vi.fn(),
    ...overrides,
  } as unknown as ReturnType<typeof apiService.getIdentityClient>;
}

function renderForm(onPasskeySignIn = vi.fn()) {
  render(
    <MemoryRouter>
      <LoginForm
        onLogin={vi.fn().mockResolvedValue(undefined)}
        onPasskeySignIn={onPasskeySignIn}
        loading={false}
        error={null}
      />
    </MemoryRouter>
  );
  return onPasskeySignIn;
}

describe('LoginForm passkeys', () => {
  beforeEach(() => {
    resetAvailabilityCache();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    resetAvailabilityCache();
  });

  it('hides the button when the browser cannot do WebAuthn', async () => {
    // No `PublicKeyCredential` on the global, which is jsdom and is also a
    // browser served over plain HTTP: WebAuthn is a secure-context API. A
    // button that throws when pressed is worse than no button.
    const fetchMock = probeFetch(200);
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(stubIdentity());

    renderForm();

    await waitFor(() => {
      expect(screen.queryByTestId('passkey-sign-in')).not.toBeInTheDocument();
    });
    // The probe is not even made: there is nothing to probe for.
    expect(passkeyProbeCount(fetchMock)).toBe(0);
  });

  it('hides the button when the options route answers 404', async () => {
    // The routes are not mounted on this backend. The brief names this case:
    // it is the availability probe, and it hides the button rather than
    // rendering an error.
    supportWebAuthn();
    const fetchMock = probeFetch(404);
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(stubIdentity());

    renderForm();

    await waitFor(() => {
      expect(passkeyProbeCount(fetchMock)).toBe(1);
    });
    expect(screen.queryByTestId('passkey-sign-in')).not.toBeInTheDocument();
  });

  it('hides the button in bearer mode, where there are no identity routes', async () => {
    supportWebAuthn();
    const fetchMock = probeFetch(200);
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(null);

    renderForm();

    await waitFor(() => {
      expect(screen.queryByTestId('passkey-sign-in')).not.toBeInTheDocument();
    });
    expect(passkeyProbeCount(fetchMock)).toBe(0);
  });

  it('signs in when the ceremony succeeds', async () => {
    supportWebAuthn();
    vi.stubGlobal('fetch', probeFetch(200));
    const outcome: PasskeySignInOutcome = {
      ok: true,
      kind: 'signed-in',
      user: { id: 1 },
      expiresIn: 900,
    };
    const signInWithPasskey = vi.fn().mockResolvedValue(outcome);
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(
      stubIdentity({ signInWithPasskey })
    );

    const onPasskeySignIn = renderForm();

    fireEvent.click(await screen.findByTestId('passkey-sign-in'));

    await waitFor(() => {
      expect(onPasskeySignIn).toHaveBeenCalledWith(outcome);
    });
    // Discoverable: no email is sent, so the authenticator offers whatever it
    // holds for this site.
    expect(signInWithPasskey).toHaveBeenCalledWith();
  });

  it('hands back an mfa-required outcome rather than signing in', async () => {
    // An authenticator that did not verify the user is one factor, so an
    // account with TOTP still needs the code step. The form does not decide
    // that; it hands the ticket to whoever owns the session.
    supportWebAuthn();
    vi.stubGlobal('fetch', probeFetch(200));
    const outcome: PasskeySignInOutcome = {
      ok: true,
      kind: 'mfa-required',
      ticket: 'ticket-1',
      factors: ['totp'],
    };
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(
      stubIdentity({ signInWithPasskey: vi.fn().mockResolvedValue(outcome) })
    );

    const onPasskeySignIn = renderForm();

    fireEvent.click(await screen.findByTestId('passkey-sign-in'));

    await waitFor(() => {
      expect(onPasskeySignIn).toHaveBeenCalledWith(outcome);
    });
  });

  it('says nothing at all when the user dismisses the prompt', async () => {
    // The package reports a dismissed browser prompt as `cancelled`, which is
    // the same gesture as closing an OAuth consent screen. A red banner for it
    // would be telling the user off for changing their mind.
    supportWebAuthn();
    vi.stubGlobal('fetch', probeFetch(200));
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(
      stubIdentity({
        signInWithPasskey: vi.fn().mockResolvedValue({
          ok: false,
          reason: 'cancelled',
          code: undefined,
          message: 'The passkey prompt was dismissed.',
        }),
      })
    );

    const onPasskeySignIn = renderForm();

    fireEvent.click(await screen.findByTestId('passkey-sign-in'));

    await waitFor(() => {
      expect(screen.getByTestId('passkey-sign-in')).not.toBeDisabled();
    });
    expect(onPasskeySignIn).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it("renders the server's own sentence for a rejection", async () => {
    supportWebAuthn();
    vi.stubGlobal('fetch', probeFetch(200));
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(
      stubIdentity({
        signInWithPasskey: vi.fn().mockResolvedValue({
          ok: false,
          reason: 'rejected',
          code: 'PASSKEY_REJECTED',
          message: 'That passkey could not be verified.',
        }),
      })
    );

    renderForm();

    fireEvent.click(await screen.findByTestId('passkey-sign-in'));

    expect(
      await screen.findByText('That passkey could not be verified.')
    ).toBeInTheDocument();
  });

  it('starts a conditional ceremony when the browser can autofill one', async () => {
    supportWebAuthn(true);
    vi.stubGlobal('fetch', probeFetch(200));
    const signInWithPasskey = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(
      stubIdentity({ signInWithPasskey })
    );

    renderForm();

    await waitFor(() => {
      expect(signInWithPasskey).toHaveBeenCalledTimes(1);
    });
    const input = signInWithPasskey.mock.calls[0]?.[0] as {
      mediation?: string;
      signal?: AbortSignal;
    };
    expect(input.mediation).toBe('conditional');
    expect(input.signal).toBeInstanceOf(AbortSignal);
    // Without the `webauthn` token the browser has nowhere to draw the passkey
    // and the conditional ceremony never becomes visible.
    expect(screen.getByLabelText('Username')).toHaveAttribute(
      'autocomplete',
      'username webauthn'
    );
  });

  it('aborts the conditional ceremony when the password form is submitted', async () => {
    // Leaving one outstanding while a password login completes is how a page
    // ends up with two sign-ins racing for the same session.
    supportWebAuthn(true);
    vi.stubGlobal('fetch', probeFetch(200));
    const signInWithPasskey = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(
      stubIdentity({ signInWithPasskey })
    );

    renderForm();

    await waitFor(() => {
      expect(signInWithPasskey).toHaveBeenCalledTimes(1);
    });
    const signal = (
      signInWithPasskey.mock.calls[0]?.[0] as { signal: AbortSignal }
    ).signal;
    expect(signal.aborted).toBe(false);

    fireEvent.change(screen.getByLabelText('Username'), {
      target: { value: 'admin' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'secret' },
    });
    fireEvent.submit(screen.getByRole('button', { name: 'Login' }));

    await waitFor(() => {
      expect(signal.aborted).toBe(true);
    });
  });

  it('does not start a conditional ceremony when the browser cannot autofill', async () => {
    supportWebAuthn(false);
    vi.stubGlobal('fetch', probeFetch(200));
    const signInWithPasskey = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(
      stubIdentity({ signInWithPasskey })
    );

    renderForm();

    // The button still appears; only the autofill ceremony is skipped.
    expect(await screen.findByTestId('passkey-sign-in')).toBeInTheDocument();
    expect(signInWithPasskey).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Username')).toHaveAttribute(
      'autocomplete',
      'username'
    );
  });
});
