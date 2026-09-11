import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LoginForm } from './LoginForm';
import { apiService } from '../../services/api';

function renderForm(onLogin = vi.fn().mockResolvedValue(undefined)) {
  render(
    <MemoryRouter>
      <LoginForm onLogin={onLogin} loading={false} error={null} />
    </MemoryRouter>
  );
  return onLogin;
}

describe('LoginForm', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('offers no forgot password affordance in bearer mode', () => {
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(null);

    renderForm();

    expect(
      screen.queryByRole('button', { name: /forgot password/i })
    ).not.toBeInTheDocument();
  });

  it('offers forgot password in identity mode', () => {
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue({
      requestPasswordReset: vi.fn(),
    } as unknown as ReturnType<typeof apiService.getIdentityClient>);

    renderForm();

    expect(
      screen.getByRole('button', { name: /forgot password/i })
    ).toBeInTheDocument();
  });

  it('signs in with whatever the two fields hold, in either mode', () => {
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(null);
    const onLogin = renderForm();

    fireEvent.change(screen.getByLabelText(/username/i), {
      target: { value: 'admin@example.test' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'secret' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^login$/i }));

    expect(onLogin).toHaveBeenCalledWith('admin@example.test', 'secret');
  });

  it('shows the same neutral sentence whether or not the address has an account', async () => {
    const request = vi.fn().mockResolvedValue({ ok: true, detail: undefined });
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue({
      requestPasswordReset: request,
    } as unknown as ReturnType<typeof apiService.getIdentityClient>);

    renderForm();
    fireEvent.click(screen.getByRole('button', { name: /forgot password/i }));
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'nobody@example.test' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/if that address has an account/i)
      ).toBeInTheDocument();
    });
    expect(request).toHaveBeenCalledWith({ email: 'nobody@example.test' });
  });

  it('keeps the neutral sentence when the request throws, so a failure discloses nothing', async () => {
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue({
      requestPasswordReset: vi.fn().mockRejectedValue(new Error('network')),
    } as unknown as ReturnType<typeof apiService.getIdentityClient>);

    renderForm();
    fireEvent.click(screen.getByRole('button', { name: /forgot password/i }));
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'someone@example.test' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/if that address has an account/i)
      ).toBeInTheDocument();
    });
  });

  it('says so on a rate limit, rather than promising a mail that is not coming', async () => {
    vi.spyOn(apiService, 'getIdentityClient').mockReturnValue({
      requestPasswordReset: vi.fn().mockResolvedValue({
        ok: false,
        reason: 'rate-limited',
        code: undefined,
        message: 'Too many requests.',
        retryAfter: 60,
      }),
    } as unknown as ReturnType<typeof apiService.getIdentityClient>);

    renderForm();
    fireEvent.click(screen.getByRole('button', { name: /forgot password/i }));
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'someone@example.test' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText(/too many requests/i)).toBeInTheDocument();
    });
  });
});
