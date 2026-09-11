import React, { useCallback, useEffect, useState } from 'react';
import type {
  Passkey,
  PasskeyDeleteOutcome,
  PasskeyListOutcome,
  PasskeyRegistrationOutcome,
  PasskeyRenameOutcome,
} from '@webbpulse/auth';

import { Button } from '../common';
import { defaultPasskeyName } from '../../services/passkeyNames';

/**
 * The passkeys on this account, with enrol, rename and remove.
 *
 * Capability is read off any call's `unavailable` outcome rather than a second
 * request. Removal asks twice because a removed credential cannot be recovered,
 * and `last-credential` disables the control with its remedy beside it.
 */

/** The subset of `AuthClient` this component calls. */
export interface PasskeysClient {
  listPasskeys: () => Promise<PasskeyListOutcome>;
  registerPasskey: (input?: {
    name?: string;
  }) => Promise<PasskeyRegistrationOutcome>;
  renamePasskey: (
    credentialId: string,
    name: string
  ) => Promise<PasskeyRenameOutcome>;
  deletePasskey: (credentialId: string) => Promise<PasskeyDeleteOutcome>;
}

interface PasskeysPanelProps {
  client: PasskeysClient;
  className?: string;
}

/**
 * A sentence per refusal reason, used when the server sends an empty message.
 *
 * The server's own sentence is preferred; these differ per reason because the
 * remedy does.
 */
const REASON_FALLBACKS: Record<string, string> = {
  'last-credential':
    'This is the only way to sign in to this account. Set a password first, then remove this passkey.',
  'already-registered':
    'That device already has a passkey for this site. Use the one it has, or remove it first.',
  rejected: 'That passkey could not be verified. Try again.',
  'not-found':
    'That passkey is not on this account any more. The list has been reloaded.',
  'name-required': 'A passkey needs a name.',
  unavailable: 'Passkeys are not available on this deployment.',
  'rate-limited': 'Too many attempts. Wait a few minutes and try again.',
};

/** The sentence to render for a refusal, preferring the server's own. */
function refusalMessage(refusal: {
  reason: string;
  message: string;
  retryAfter?: number | undefined;
}): string {
  const base =
    refusal.message.trim() !== ''
      ? refusal.message
      : (REASON_FALLBACKS[refusal.reason] ?? 'That request was refused.');
  if (refusal.reason === 'rate-limited' && refusal.retryAfter !== undefined) {
    return `${base} Try again in ${refusal.retryAfter} seconds.`;
  }
  return base;
}

/** An ISO instant as a readable date, or nothing when the server sent none. */
function formatInstant(value: string | undefined): string | null {
  if (value === undefined || value === '') {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toLocaleDateString();
}

/** One enrolled passkey, with its dates, its rename and its removal. */
const PasskeyRow: React.FC<{
  passkey: Passkey;
  busy: boolean;
  /** The `last-credential` explanation, when the last delete hit it. */
  blockedReason: string | null;
  onRename: (name: string) => void;
  onDelete: () => void;
}> = ({ passkey, busy, blockedReason, onRename, onDelete }) => {
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(passkey.name);
  const [confirming, setConfirming] = useState(false);

  const createdAt = formatInstant(passkey.createdAt);
  const lastUsedAt = formatInstant(passkey.lastUsedAt);

  return (
    <li
      data-testid={`passkey-${passkey.credentialId}`}
      className="flex flex-wrap items-center justify-between gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded"
    >
      {renaming ? (
        <form
          className="flex flex-wrap items-center gap-2 w-full"
          onSubmit={e => {
            e.preventDefault();
            onRename(draft.trim());
            setRenaming(false);
          }}
        >
          <label
            htmlFor={`passkey-name-${passkey.credentialId}`}
            className="text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Name
          </label>
          <input
            id={`passkey-name-${passkey.credentialId}`}
            type="text"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            maxLength={64}
            className="flex-1 min-w-[12rem] px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
            required
            disabled={busy}
          />
          <Button type="submit" variant="primary" size="sm" disabled={busy}>
            Save
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setDraft(passkey.name);
              setRenaming(false);
            }}
            disabled={busy}
          >
            Cancel
          </Button>
        </form>
      ) : (
        <>
          <div>
            <p className="text-base font-medium text-gray-900 dark:text-white">
              {passkey.name === '' ? 'Passkey' : passkey.name}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-500">
              {createdAt === null ? 'Added' : `Added ${createdAt}`}
              {lastUsedAt === null
                ? ', never used'
                : `, last used ${lastUsedAt}`}
            </p>
            {blockedReason !== null && (
              <p
                data-testid={`passkey-blocked-${passkey.credentialId}`}
                className="mt-1 text-sm text-amber-700 dark:text-amber-400"
              >
                {blockedReason}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setDraft(passkey.name);
                setRenaming(true);
              }}
              disabled={busy}
            >
              Rename
            </Button>
            {confirming ? (
              <>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    setConfirming(false);
                    onDelete();
                  }}
                  disabled={busy || blockedReason !== null}
                >
                  Confirm removal
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setConfirming(false)}
                  disabled={busy}
                >
                  Keep it
                </Button>
              </>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setConfirming(true)}
                disabled={busy || blockedReason !== null}
              >
                Remove
              </Button>
            )}
          </div>
        </>
      )}
    </li>
  );
};

/** Renders the enrolled passkeys and the enrol, rename and remove controls. */
export const PasskeysPanel: React.FC<PasskeysPanelProps> = ({
  client,
  className = '',
}) => {
  const [passkeys, setPasskeys] = useState<Passkey[] | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [naming, setNaming] = useState(false);
  const [newName, setNewName] = useState('');

  /**
   * The credential the server refused to remove, and why.
   *
   * Held per credential rather than as one flag, and cleared on every reload, so
   * enrolling a second passkey re-enables the first one's Remove.
   */
  const [blocked, setBlocked] = useState<Record<string, string>>({});

  const reload = useCallback(async () => {
    try {
      const outcome = await client.listPasskeys();
      if (outcome.ok) {
        setPasskeys(outcome.passkeys);
        setUnavailable(false);
        setBlocked({});
        return;
      }
      setPasskeys([]);
      setUnavailable(true);
    } catch {
      setPasskeys([]);
      setError('Your passkeys could not be loaded. Try again.');
    }
  }, [client]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleRegister = useCallback(
    async (name: string) => {
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const outcome = await client.registerPasskey(
          name === '' ? {} : { name }
        );
        if (outcome.ok) {
          setNaming(false);
          setNotice(`${outcome.passkey.name} is ready to sign in with.`);
          await reload();
          return;
        }
        if (outcome.reason === 'cancelled') {
          setNaming(false);
          return;
        }
        setError(refusalMessage(outcome));
      } catch {
        setError('That passkey could not be added. Try again.');
      } finally {
        setBusy(false);
      }
    },
    [client, reload]
  );

  const handleRename = useCallback(
    async (credentialId: string, name: string) => {
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const outcome = await client.renamePasskey(credentialId, name);
        if (outcome.ok) {
          setPasskeys(current =>
            (current ?? []).map(entry =>
              entry.credentialId === credentialId ? outcome.passkey : entry
            )
          );
          setNotice('That passkey was renamed.');
          return;
        }
        setError(refusalMessage(outcome));
        if (outcome.reason === 'not-found') {
          await reload();
        }
      } catch {
        setError('That passkey could not be renamed. Try again.');
      } finally {
        setBusy(false);
      }
    },
    [client, reload]
  );

  const handleDelete = useCallback(
    async (credentialId: string) => {
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const outcome = await client.deletePasskey(credentialId);
        if (outcome.ok) {
          setNotice('That passkey was removed.');
          await reload();
          return;
        }
        const message = refusalMessage(outcome);
        setError(message);
        if (outcome.reason === 'last-credential') {
          setBlocked(current => ({ ...current, [credentialId]: message }));
        }
        if (outcome.reason === 'not-found') {
          await reload();
        }
      } catch {
        setError('That passkey could not be removed. Try again.');
      } finally {
        setBusy(false);
      }
    },
    [client, reload]
  );

  const list = passkeys ?? [];

  return (
    <div className={className} data-testid="passkeys-panel">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
        Passkeys
      </h3>
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
        Sign in with your device unlock instead of a password. A passkey that
        verified you counts as both factors, so it skips the code step. Removing
        the only way in to this account is refused, so set a password before
        removing the last one.
      </p>

      {error !== null && (
        <div
          role="alert"
          className="mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded"
        >
          {error}
        </div>
      )}
      {notice !== null && (
        <div
          role="status"
          className="mb-4 p-3 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 rounded"
        >
          {notice}
        </div>
      )}

      {unavailable ? (
        <p
          data-testid="passkeys-unavailable"
          className="text-sm text-gray-600 dark:text-gray-400"
        >
          Passkeys are not switched on for this deployment.
        </p>
      ) : passkeys === null ? (
        <p className="text-sm text-gray-600 dark:text-gray-400">Loading...</p>
      ) : (
        <>
          {list.length === 0 ? (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              No passkeys are set up on this account.
            </p>
          ) : (
            <ul className="space-y-3 mb-4">
              {list.map(passkey => (
                <PasskeyRow
                  key={passkey.credentialId}
                  passkey={passkey}
                  busy={busy}
                  blockedReason={blocked[passkey.credentialId] ?? null}
                  onRename={name =>
                    void handleRename(passkey.credentialId, name)
                  }
                  onDelete={() => void handleDelete(passkey.credentialId)}
                />
              ))}
            </ul>
          )}

          {naming ? (
            <form
              className="mt-4 space-y-3 p-4 border border-gray-200 dark:border-gray-700 rounded max-w-md"
              onSubmit={e => {
                e.preventDefault();
                void handleRegister(newName.trim());
              }}
            >
              <label
                htmlFor="new-passkey-name"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Name this passkey
              </label>
              <input
                id="new-passkey-name"
                type="text"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                maxLength={64}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                disabled={busy}
              />
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Something you will recognise in this list later. Your browser
                will ask for your device unlock next.
              </p>
              <div className="flex gap-3">
                <Button type="submit" variant="primary" disabled={busy}>
                  {busy ? 'Waiting for your device...' : 'Add passkey'}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setNaming(false);
                    setError(null);
                  }}
                  disabled={busy}
                >
                  Cancel
                </Button>
              </div>
            </form>
          ) : (
            <Button
              variant="primary"
              onClick={() => {
                setNewName(defaultPasskeyName());
                setNaming(true);
                setError(null);
                setNotice(null);
              }}
              disabled={busy}
            >
              Add a passkey
            </Button>
          )}
        </>
      )}
    </div>
  );
};
