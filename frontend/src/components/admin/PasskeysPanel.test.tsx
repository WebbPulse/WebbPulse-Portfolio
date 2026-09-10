import { describe, expect, it, vi } from 'vitest';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';

import { PasskeysPanel, type PasskeysClient } from './PasskeysPanel';
import { defaultPasskeyName } from '../../services/passkeyNames';

// The identity client is stubbed rather than the transport, for the reason
// `ConnectedAccounts.test.tsx` gives: `@webbpulse/auth` already tests turning a
// response into an outcome, and this file's subject is the reaction. What is
// worth pinning down is `last-credential`, the one refusal whose remedy is a
// specific instruction, and the cancellation that must not read as a failure.

function stubClient(overrides: Partial<PasskeysClient> = {}): PasskeysClient {
  return {
    listPasskeys: vi.fn().mockResolvedValue({ ok: true, passkeys: [] }),
    registerPasskey: vi.fn(),
    renamePasskey: vi.fn(),
    deletePasskey: vi.fn(),
    ...overrides,
  };
}

/** A passkey in the shape `parsePasskey` produces. */
function passkey(credentialId: string, overrides = {}) {
  return {
    credentialId,
    name: 'MacBook Touch ID',
    createdAt: '2026-09-01T00:00:00Z',
    lastUsedAt: '2026-09-08T00:00:00Z',
    transports: ['internal'],
    aaguid: '',
    backupEligible: false,
    backupState: false,
    userVerified: true,
    ...overrides,
  };
}

/** A refusal in the shape the package's outcome union produces. */
function refusal(reason: string, message = '') {
  return { ok: false as const, reason, message, code: undefined };
}

describe('PasskeysPanel', () => {
  it('lists the passkeys on the account with their dates', async () => {
    const client = stubClient({
      listPasskeys: vi
        .fn()
        .mockResolvedValue({ ok: true, passkeys: [passkey('cred-1')] }),
    });

    render(<PasskeysPanel client={client} />);

    expect(await screen.findByTestId('passkey-cred-1')).toBeInTheDocument();
    expect(screen.getByText('MacBook Touch ID')).toBeInTheDocument();
    expect(screen.getByText(/last used/i)).toBeInTheDocument();
  });

  it('says a passkey has never been used when the server sent no instant', async () => {
    const client = stubClient({
      listPasskeys: vi.fn().mockResolvedValue({
        ok: true,
        passkeys: [passkey('cred-1', { lastUsedAt: undefined })],
      }),
    });

    render(<PasskeysPanel client={client} />);

    expect(await screen.findByText(/never used/i)).toBeInTheDocument();
  });

  it('says so when nothing is enrolled', async () => {
    render(<PasskeysPanel client={stubClient()} />);

    expect(
      await screen.findByText(/no passkeys are set up/i)
    ).toBeInTheDocument();
  });

  it('renders a sentence rather than an empty panel when the capability is off', async () => {
    // A backend without passkeys must not look like an account without them.
    const client = stubClient({
      listPasskeys: vi.fn().mockResolvedValue(refusal('unavailable')),
    });

    render(<PasskeysPanel client={client} />);

    expect(
      await screen.findByTestId('passkeys-unavailable')
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /add a passkey/i })
    ).not.toBeInTheDocument();
  });

  it('registers a passkey under the name the user confirmed', async () => {
    const registerPasskey = vi
      .fn()
      .mockResolvedValue({ ok: true, passkey: passkey('cred-1') });
    const listPasskeys = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, passkeys: [] })
      .mockResolvedValue({ ok: true, passkeys: [passkey('cred-1')] });
    const client = stubClient({ registerPasskey, listPasskeys });

    render(<PasskeysPanel client={client} />);

    fireEvent.click(
      await screen.findByRole('button', { name: /add a passkey/i })
    );
    fireEvent.change(screen.getByLabelText(/name this passkey/i), {
      target: { value: 'Yubikey' },
    });
    fireEvent.click(screen.getByRole('button', { name: /add passkey/i }));

    await waitFor(() => {
      expect(registerPasskey).toHaveBeenCalledWith({ name: 'Yubikey' });
    });
    // The list is reloaded rather than patched, because enrolment is the one
    // call that can change another row's `last-credential` standing.
    expect(await screen.findByTestId('passkey-cred-1')).toBeInTheDocument();
  });

  it('prefills a name from the platform hint', () => {
    expect(defaultPasskeyName('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)')).toBe(
      'iPhone'
    );
    expect(defaultPasskeyName('Mozilla/5.0 (Macintosh; Intel Mac OS X)')).toBe(
      'Mac'
    );
    expect(defaultPasskeyName('Mozilla/5.0 (Windows NT 10.0; Win64)')).toBe(
      'Windows Hello'
    );
    // A user agent this build has never seen still gets something typeable.
    expect(defaultPasskeyName('Something/1.0')).toBe('Passkey');
  });

  it('says nothing when the user dismisses the enrolment prompt', async () => {
    const client = stubClient({
      registerPasskey: vi.fn().mockResolvedValue({
        ok: false,
        reason: 'cancelled',
        code: undefined,
        message: 'The passkey prompt was dismissed.',
      }),
    });

    render(<PasskeysPanel client={client} />);

    fireEvent.click(
      await screen.findByRole('button', { name: /add a passkey/i })
    );
    fireEvent.click(screen.getByRole('button', { name: /add passkey/i }));

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /add a passkey/i })
      ).toBeInTheDocument();
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renames a passkey and patches the row from the response', async () => {
    const renamePasskey = vi.fn().mockResolvedValue({
      ok: true,
      passkey: passkey('cred-1', { name: 'Work laptop' }),
    });
    const client = stubClient({
      listPasskeys: vi
        .fn()
        .mockResolvedValue({ ok: true, passkeys: [passkey('cred-1')] }),
      renamePasskey,
    });

    render(<PasskeysPanel client={client} />);

    fireEvent.click(await screen.findByRole('button', { name: /rename/i }));
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Work laptop' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(renamePasskey).toHaveBeenCalledWith('cred-1', 'Work laptop');
    });
    expect(await screen.findByText('Work laptop')).toBeInTheDocument();
  });

  it('removes a passkey only after a confirmation', async () => {
    const deletePasskey = vi.fn().mockResolvedValue({ ok: true });
    const listPasskeys = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        passkeys: [passkey('cred-1'), passkey('cred-2')],
      })
      .mockResolvedValue({ ok: true, passkeys: [passkey('cred-2')] });
    const client = stubClient({ listPasskeys, deletePasskey });

    render(<PasskeysPanel client={client} />);

    const row = await screen.findByTestId('passkey-cred-1');
    // Scoped to the row under test: with two enrolled there are two Remove
    // controls, and the assertion below is about this one.
    fireEvent.click(within(row).getByRole('button', { name: 'Remove' }));
    // The first press only asks. A passkey cannot be recovered once removed.
    expect(deletePasskey).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /confirm removal/i }));

    await waitFor(() => {
      expect(deletePasskey).toHaveBeenCalledWith('cred-1');
    });
    await waitFor(() => {
      expect(screen.queryByTestId('passkey-cred-1')).not.toBeInTheDocument();
    });
  });

  it('disables the removal and explains when it is the last way in', async () => {
    // `last-credential` is the refusal with a remedy: the account has no
    // password, so removing this would strand the user outside it. The control
    // stops offering something that cannot work, and says why.
    const client = stubClient({
      listPasskeys: vi
        .fn()
        .mockResolvedValue({ ok: true, passkeys: [passkey('cred-1')] }),
      deletePasskey: vi
        .fn()
        .mockResolvedValue(
          refusal(
            'last-credential',
            'This is the only way to sign in to this account.'
          )
        ),
    });

    render(<PasskeysPanel client={client} />);

    await screen.findByTestId('passkey-cred-1');
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    fireEvent.click(screen.getByRole('button', { name: /confirm removal/i }));

    expect(
      await screen.findByTestId('passkey-blocked-cred-1')
    ).toHaveTextContent('This is the only way to sign in to this account.');
    expect(screen.getByRole('button', { name: 'Remove' })).toBeDisabled();
  });

  it('writes its own sentence for last-credential when the server sends none', async () => {
    // The remedy is a specific instruction and no generic toast knows to say
    // it, so the fallback names the password step.
    const client = stubClient({
      listPasskeys: vi
        .fn()
        .mockResolvedValue({ ok: true, passkeys: [passkey('cred-1')] }),
      deletePasskey: vi.fn().mockResolvedValue(refusal('last-credential')),
    });

    render(<PasskeysPanel client={client} />);

    await screen.findByTestId('passkey-cred-1');
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    fireEvent.click(screen.getByRole('button', { name: /confirm removal/i }));

    expect(
      await screen.findByTestId('passkey-blocked-cred-1')
    ).toHaveTextContent(/set a password first/i);
  });

  it('reloads the list when a rename hits a stale row', async () => {
    const listPasskeys = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, passkeys: [passkey('cred-1')] })
      .mockResolvedValue({ ok: true, passkeys: [] });
    const client = stubClient({
      listPasskeys,
      renamePasskey: vi.fn().mockResolvedValue(refusal('not-found')),
    });

    render(<PasskeysPanel client={client} />);

    fireEvent.click(await screen.findByRole('button', { name: /rename/i }));
    fireEvent.change(screen.getByLabelText('Name'), {
      target: { value: 'Gone' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(listPasskeys).toHaveBeenCalledTimes(2);
    });
  });
});
