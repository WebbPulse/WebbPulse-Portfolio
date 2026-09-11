import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { VerifyEmail } from './VerifyEmail';
import { apiService } from '../services/api';

// What is worth pinning down here is the mapping from the four outcomes the
// confirm route can answer with onto what the user is told, and the two guards
// that keep a single use token from being wasted: the strict mode double
// effect, and a token belonging to the other flow.
//
// The identity client is stubbed rather than the transport, because the
// package's own tests already cover turning a response into an outcome. This
// file's subject is the page's reaction to each one.

/** A stub standing in for the parts of `AuthClient` this page touches. */
function stubIdentity(confirm: ReturnType<typeof vi.fn>) {
  vi.spyOn(apiService, 'getIdentityClient').mockReturnValue({
    confirmEmailVerification: confirm,
  } as unknown as ReturnType<typeof apiService.getIdentityClient>);
}

function renderAt(url: string) {
  // The page reads the token off the real location rather than the router, so
  // the address bar is what has to carry it.
  window.history.replaceState({}, '', url);
  return render(
    <MemoryRouter>
      <VerifyEmail />
    </MemoryRouter>
  );
}

describe('VerifyEmail', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('confirms the token from the link and reports success', async () => {
    const confirm = vi.fn().mockResolvedValue({ ok: true, userId: 'u1' });
    stubIdentity(confirm);

    renderAt('/verify-email?token=abc123');

    await waitFor(() => {
      expect(screen.getByText(/verified/i)).toBeInTheDocument();
    });
    expect(confirm).toHaveBeenCalledWith({ token: 'abc123' });
  });

  it('confirms only once, so a strict mode double effect cannot spend the token twice', async () => {
    const confirm = vi.fn().mockResolvedValue({ ok: true, userId: null });
    stubIdentity(confirm);

    const { rerender } = renderAt('/verify-email?token=abc123');
    rerender(
      <MemoryRouter>
        <VerifyEmail />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/verified/i)).toBeInTheDocument();
    });
    expect(confirm).toHaveBeenCalledTimes(1);
  });

  it('tells the user a spent or expired link is no longer valid', async () => {
    stubIdentity(
      vi.fn().mockResolvedValue({
        ok: false,
        reason: 'invalid-link',
        code: undefined,
        message: 'Invalid link.',
        retryAfter: undefined,
      })
    );

    renderAt('/verify-email?token=stale');

    await waitFor(() => {
      expect(screen.getByText(/no longer valid/i)).toBeInTheDocument();
    });
  });

  it('distinguishes a rate limit from an invalid link', async () => {
    stubIdentity(
      vi.fn().mockResolvedValue({
        ok: false,
        reason: 'rate-limited',
        code: undefined,
        message: 'Too many requests.',
        retryAfter: 60,
      })
    );

    renderAt('/verify-email?token=abc123');

    await waitFor(() => {
      expect(screen.getByText(/too many attempts/i)).toBeInTheDocument();
    });
  });

  it('reports a deployment with no sender as unavailable rather than as the user fault', async () => {
    stubIdentity(
      vi.fn().mockResolvedValue({
        ok: false,
        reason: 'unavailable',
        code: undefined,
        message: 'Email is not configured.',
        retryAfter: undefined,
      })
    );

    renderAt('/verify-email?token=abc123');

    await waitFor(() => {
      expect(screen.getByText(/not available right now/i)).toBeInTheDocument();
    });
  });

  it('does not call the route at all when the link carries no token', async () => {
    const confirm = vi.fn();
    stubIdentity(confirm);

    renderAt('/verify-email');

    await waitFor(() => {
      expect(screen.getByText(/missing its token/i)).toBeInTheDocument();
    });
    expect(confirm).not.toHaveBeenCalled();
  });

  it('refuses a token that arrived on the reset path, which the server would reject as the wrong purpose', async () => {
    const confirm = vi.fn();
    stubIdentity(confirm);

    renderAt('/reset-password?token=reset-token');

    await waitFor(() => {
      expect(screen.getByText(/missing its token/i)).toBeInTheDocument();
    });
    expect(confirm).not.toHaveBeenCalled();
  });

  it('says the flow is not enabled in bearer mode', async () => {
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(null);

    renderAt('/verify-email?token=abc123');

    await waitFor(() => {
      expect(screen.getByText(/not enabled/i)).toBeInTheDocument();
    });
  });
});
