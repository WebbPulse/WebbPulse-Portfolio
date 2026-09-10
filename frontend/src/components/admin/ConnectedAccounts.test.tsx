import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { ConnectedAccounts, type OAuthLinksClient } from './ConnectedAccounts';

// The identity client is stubbed rather than the transport, for the reason
// `SecuritySection.test.tsx` gives: `@webbpulse/auth` already tests turning a
// response into an outcome, and this file's subject is the reaction. What is
// worth pinning down is the `last-sign-in-method` refusal, which is the one
// refusal whose remedy is a specific instruction rather than "try again", and
// the split between what is linked and what can be linked.

function stubClient(
  overrides: Partial<OAuthLinksClient> = {}
): OAuthLinksClient {
  return {
    listOAuthLinks: vi.fn().mockResolvedValue({ ok: true, links: [] }),
    linkOAuthProvider: vi.fn(),
    unlinkOAuthProvider: vi.fn(),
    ...overrides,
  };
}

/** A link in the shape `parseOAuthLinks` produces. */
function link(provider: string, overrides = {}) {
  return {
    provider,
    email: `someone@${provider}.test`,
    emailVerified: true,
    linkedAt: '2026-09-01T00:00:00Z',
    lastLoginAt: '2026-09-08T00:00:00Z',
    ...overrides,
  };
}

/** A refusal in the shape the package's outcome union produces. */
function refusal(reason: string, message = '') {
  return { ok: false as const, reason, message, code: undefined };
}

describe('ConnectedAccounts', () => {
  it('lists the links the account has', async () => {
    const client = stubClient({
      listOAuthLinks: vi
        .fn()
        .mockResolvedValue({ ok: true, links: [link('google')] }),
    });

    render(<ConnectedAccounts client={client} availableProviders={[]} />);

    expect(await screen.findByTestId('oauth-link-google')).toBeInTheDocument();
    expect(screen.getByText('someone@google.test')).toBeInTheDocument();
  });

  it('says so when nothing is connected', async () => {
    render(<ConnectedAccounts client={stubClient()} availableProviders={[]} />);

    expect(
      await screen.findByText(/no providers are connected/i)
    ).toBeInTheDocument();
  });

  it('offers a connect button only for an available, unlinked provider', async () => {
    const client = stubClient({
      listOAuthLinks: vi
        .fn()
        .mockResolvedValue({ ok: true, links: [link('google')] }),
    });

    render(
      <ConnectedAccounts
        client={client}
        availableProviders={['google', 'github']}
      />
    );

    await screen.findByTestId('oauth-link-google');
    // Google is already linked, so only GitHub is offered.
    expect(
      screen.getByRole('button', { name: /connect github/i })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /connect google/i })
    ).not.toBeInTheDocument();
  });

  it('still lists a linked provider that is no longer configured', async () => {
    // The user must be able to unlink it even though it cannot be linked
    // again, which is why availability gates only the attach affordance.
    const client = stubClient({
      listOAuthLinks: vi
        .fn()
        .mockResolvedValue({ ok: true, links: [link('github')] }),
    });

    render(<ConnectedAccounts client={client} availableProviders={[]} />);

    expect(await screen.findByTestId('oauth-link-github')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /disconnect/i })
    ).toBeInTheDocument();
  });

  it('sends the browser to the authorization URL on a successful link', async () => {
    const navigate = vi.fn();
    const client = stubClient({
      linkOAuthProvider: vi.fn().mockResolvedValue({
        ok: true,
        authorizationUrl: 'https://github.test/authorize?state=abc',
      }),
    });

    render(
      <ConnectedAccounts
        client={client}
        availableProviders={['github']}
        navigate={navigate}
      />
    );

    fireEvent.click(
      await screen.findByRole('button', { name: /connect github/i })
    );

    await waitFor(() => {
      expect(navigate).toHaveBeenCalledWith(
        'https://github.test/authorize?state=abc'
      );
    });
  });

  it('renders the server sentence for a last-sign-in-method refusal', async () => {
    // The remedy is "set a password first", which no generic failure toast
    // says, and the server's own sentence is the one to show.
    const message =
      'This is the only way to sign in to this account. Set a password first.';
    const client = stubClient({
      listOAuthLinks: vi
        .fn()
        .mockResolvedValue({ ok: true, links: [link('google')] }),
      unlinkOAuthProvider: vi
        .fn()
        .mockResolvedValue(refusal('last-sign-in-method', message)),
    });

    render(<ConnectedAccounts client={client} availableProviders={[]} />);

    fireEvent.click(await screen.findByRole('button', { name: /disconnect/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
  });

  it('falls back to a local sentence when the server sends an empty message', async () => {
    const client = stubClient({
      listOAuthLinks: vi
        .fn()
        .mockResolvedValue({ ok: true, links: [link('google')] }),
      unlinkOAuthProvider: vi
        .fn()
        .mockResolvedValue(refusal('last-sign-in-method', '')),
    });

    render(<ConnectedAccounts client={client} availableProviders={[]} />);

    fireEvent.click(await screen.findByRole('button', { name: /disconnect/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /set a password first/i
    );
  });

  it('reloads the list after a successful unlink', async () => {
    const listOAuthLinks = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, links: [link('google')] })
      .mockResolvedValueOnce({ ok: true, links: [] });
    const client = stubClient({
      listOAuthLinks,
      unlinkOAuthProvider: vi.fn().mockResolvedValue({ ok: true }),
    });

    render(<ConnectedAccounts client={client} availableProviders={[]} />);

    fireEvent.click(await screen.findByRole('button', { name: /disconnect/i }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      /google is no longer connected/i
    );
    expect(
      await screen.findByText(/no providers are connected/i)
    ).toBeInTheDocument();
  });

  it('reloads on a not-linked refusal, which means the list was stale', async () => {
    const listOAuthLinks = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, links: [link('google')] })
      .mockResolvedValueOnce({ ok: true, links: [] });
    const client = stubClient({
      listOAuthLinks,
      unlinkOAuthProvider: vi.fn().mockResolvedValue(refusal('not-linked', '')),
    });

    render(<ConnectedAccounts client={client} availableProviders={[]} />);

    fireEvent.click(await screen.findByRole('button', { name: /disconnect/i }));

    await waitFor(() => {
      expect(listOAuthLinks).toHaveBeenCalledTimes(2);
    });
  });

  it('reports a list that could not be loaded', async () => {
    const client = stubClient({
      listOAuthLinks: vi.fn().mockRejectedValue(new Error('network')),
    });

    render(<ConnectedAccounts client={client} availableProviders={[]} />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /could not be loaded/i
    );
  });
});
