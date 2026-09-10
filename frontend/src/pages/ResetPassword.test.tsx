import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ResetPassword } from './ResetPassword';
import { apiService } from '../services/api';

// The properties worth holding here are the ones a careless rewrite would
// lose: the token is spent only on submit and only when the two fields agree,
// each refusal gets its own remedy, and a success ends at the sign in form
// rather than in the panel, because the reset revoked every session.

function stubIdentity(confirm: ReturnType<typeof vi.fn>) {
  vi.spyOn(apiService, 'getIdentityClient').mockReturnValue({
    confirmPasswordReset: confirm,
  } as unknown as ReturnType<typeof apiService.getIdentityClient>);
}

function renderAt(url: string) {
  window.history.replaceState({}, '', url);
  return render(
    <MemoryRouter>
      <ResetPassword />
    </MemoryRouter>
  );
}

/**
 * Fills both fields and submits.
 *
 * `fireEvent` rather than `user-event`, which this repository does not depend
 * on. A controlled input only needs its change event for the value to land in
 * state, and the assertions here are about what the page did with that value.
 */
function submit(password: string, confirmation: string) {
  fireEvent.change(screen.getByLabelText(/^new password$/i), {
    target: { value: password },
  });
  fireEvent.change(screen.getByLabelText(/confirm new password/i), {
    target: { value: confirmation },
  });
  fireEvent.click(screen.getByRole('button', { name: /set new password/i }));
}

describe('ResetPassword', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends the token and the new password, then points the user at sign in', async () => {
    const confirm = vi.fn().mockResolvedValue({ ok: true });
    stubIdentity(confirm);

    renderAt('/reset-password?token=abc123');
    submit('correct horse battery', 'correct horse battery');

    await waitFor(() => {
      expect(screen.getByText(/password is updated/i)).toBeInTheDocument();
    });
    expect(confirm).toHaveBeenCalledWith({
      token: 'abc123',
      newPassword: 'correct horse battery',
    });
  });

  it('does not spend the token when the confirmation does not match', async () => {
    const confirm = vi.fn();
    stubIdentity(confirm);

    renderAt('/reset-password?token=abc123');
    submit('one password', 'another password');

    await waitFor(() => {
      expect(screen.getByText(/do not match/i)).toBeInTheDocument();
    });
    expect(confirm).not.toHaveBeenCalled();
  });

  it('tells the user to request a new link when this one is spent', async () => {
    stubIdentity(
      vi.fn().mockResolvedValue({
        ok: false,
        reason: 'invalid-link',
        code: undefined,
        message: 'Invalid link.',
        retryAfter: undefined,
      })
    );

    renderAt('/reset-password?token=stale');
    submit('a new password', 'a new password');

    await waitFor(() => {
      expect(screen.getByText(/no longer valid/i)).toBeInTheDocument();
    });
  });

  it('shows the server sentence for a rejected password, and says the link is now spent', async () => {
    stubIdentity(
      vi.fn().mockResolvedValue({
        ok: false,
        reason: 'password-rejected',
        code: undefined,
        message: 'Password is too short.',
        retryAfter: undefined,
      })
    );

    renderAt('/reset-password?token=abc123');
    submit('short', 'short');

    await waitFor(() => {
      expect(screen.getByText(/too short/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/request a new one/i)).toBeInTheDocument();
  });

  it('reports a rate limit as something to wait out', async () => {
    stubIdentity(
      vi.fn().mockResolvedValue({
        ok: false,
        reason: 'rate-limited',
        code: undefined,
        message: 'Too many requests.',
        retryAfter: 60,
      })
    );

    renderAt('/reset-password?token=abc123');
    submit('a new password', 'a new password');

    await waitFor(() => {
      expect(screen.getByText(/too many attempts/i)).toBeInTheDocument();
    });
  });

  it('shows no form at all when the link carries no token', () => {
    stubIdentity(vi.fn());

    renderAt('/reset-password');

    expect(screen.getByText(/missing its token/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^new password$/i)).not.toBeInTheDocument();
  });

  it('refuses a token that arrived on the verification path', () => {
    stubIdentity(vi.fn());

    renderAt('/verify-email?token=verify-token');

    expect(screen.getByText(/missing its token/i)).toBeInTheDocument();
  });

  it('says the flow is not enabled in bearer mode', () => {
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(null);

    renderAt('/reset-password?token=abc123');

    expect(screen.getByText(/not enabled/i)).toBeInTheDocument();
  });
});
