import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { PasskeySignInOutcome } from '@webbpulse/auth';

import { resetAvailabilityCache } from '@webbpulse/discovery';

import { LoginForm } from './LoginForm';
import { apiService } from '../../services/api';

/** Puts a `PublicKeyCredential` on the global, as a real browser has. */
function supportWebAuthn(conditional = false): void {
  vi.stubGlobal('PublicKeyCredential', {
    isConditionalMediationAvailable: () => Promise.resolve(conditional),
  });
}

/**
 * A fetch that answers the passkey availability route with `status`.
 *
 * Helpers filter by URL because the OAuth gate shares this global. A fresh
 * `Response` per call, since a body can only be read once.
 */
function availabilityFetch(
  status: number,
  body: unknown = { enabled: true, passwordless: true }
) {
  return vi.fn().mockImplementation(() =>
    Promise.resolve(
      new Response(status === 404 ? null : JSON.stringify(body), {
        status,
        ...(status === 404
          ? {}
          : { headers: { 'content-type': 'application/json' } }),
      })
    )
  );
}

/** How many times the passkey availability route was asked. */
function passkeyProbeCount(fetchMock: ReturnType<typeof vi.fn>): number {
  return fetchMock.mock.calls.filter((call) =>
    String(call[0]).includes('/api/auth/passkeys/availability')
  ).length;
}

/** The one `AuthClient` method these passkey tests reach. */
function stubIdentity(overrides: Record<string, unknown> = {}) {
  return {
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
  });

  it('hides the button when the browser cannot do WebAuthn', async () => {
    const fetchMock = availabilityFetch(200);
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(stubIdentity());

    renderForm();

    await waitFor(() => {
      expect(screen.queryByTestId('passkey-sign-in')).not.toBeInTheDocument();
    });
    expect(passkeyProbeCount(fetchMock)).toBe(0);
  });

  it('hides the button when the availability route answers 404', async () => {
    supportWebAuthn();
    const fetchMock = availabilityFetch(404);
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(stubIdentity());

    renderForm();

    await waitFor(() => {
      expect(passkeyProbeCount(fetchMock)).toBe(1);
    });
    expect(screen.queryByTestId('passkey-sign-in')).not.toBeInTheDocument();
  });

  it('hides the button where passkeys are on but not a way in', async () => {
    supportWebAuthn();
    const fetchMock = availabilityFetch(200, {
      enabled: true,
      passwordless: false,
    });
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
    const fetchMock = availabilityFetch(200);
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
    vi.stubGlobal('fetch', availabilityFetch(200));
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
    expect(signInWithPasskey).toHaveBeenCalledWith();
  });

  it('hands back an mfa-required outcome rather than signing in', async () => {
    supportWebAuthn();
    vi.stubGlobal('fetch', availabilityFetch(200));
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
    supportWebAuthn();
    vi.stubGlobal('fetch', availabilityFetch(200));
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
    vi.stubGlobal('fetch', availabilityFetch(200));
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
    vi.stubGlobal('fetch', availabilityFetch(200));
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
    expect(screen.getByLabelText('Username')).toHaveAttribute(
      'autocomplete',
      'username webauthn'
    );
  });

  it('aborts the conditional ceremony when the password form is submitted', async () => {
    supportWebAuthn(true);
    vi.stubGlobal('fetch', availabilityFetch(200));
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
    vi.stubGlobal('fetch', availabilityFetch(200));
    const signInWithPasskey = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(
      stubIdentity({ signInWithPasskey })
    );

    renderForm();

    expect(await screen.findByTestId('passkey-sign-in')).toBeInTheDocument();
    expect(signInWithPasskey).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Username')).toHaveAttribute(
      'autocomplete',
      'username'
    );
  });
});
