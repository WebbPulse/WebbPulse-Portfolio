import React, { useMemo, useState } from 'react';
import type { AuthClient, Passkey } from '@webbpulse/auth';
import { usePasskeyPanel } from '@webbpulse/auth/panels';

import { Button } from '../common';
import { defaultPasskeyName } from '../../services/passkeyNames';

/**
 * The passkeys on this account, with enrol, rename and remove.
 *
 * State comes from `usePasskeyPanel`, so capability, busy, the banners and the
 * two drafts are the package's. Removal asks twice because a removed credential
 * cannot be recovered, and the confirmation is the only state left here.
 */

/** The subset of `AuthClient` this component calls. */
export type PasskeysClient = AuthClient<unknown>;

interface PasskeysPanelProps {
  client: PasskeysClient;
  className?: string;
}

/** The sentence for a `last-credential` refusal, preferring the server's own. */
function refusalMessage(refusal: { message: string }): string {
  return refusal.message.trim() !== ''
    ? refusal.message
    : 'This is the only way to sign in to this account. Set a password first, then remove this passkey.';
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
  /** Whether the rename form is open on this row. */
  renaming: boolean;
  /** The rename draft, owned by the panel hook. */
  draft: string;
  onDraftChange: (name: string) => void;
  onStartRename: () => void;
  onCancelRename: () => void;
  onCommitRename: () => void;
  onDelete: () => void;
}> = ({
  passkey,
  busy,
  blockedReason,
  renaming,
  draft,
  onDraftChange,
  onStartRename,
  onCancelRename,
  onCommitRename,
  onDelete,
}) => {
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
          onSubmit={(e) => {
            e.preventDefault();
            onCommitRename();
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
            onChange={(e) => onDraftChange(e.target.value)}
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
            onClick={onCancelRename}
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
              onClick={onStartRename}
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
  /**
   * The credential the server refused to remove, and why.
   *
   * The hook reduces a refusal to a sentence without saying which row it was
   * about, so the delete call is observed here to attribute `last-credential` to
   * its row. Cleared on every reload, so enrolling a second passkey re-enables
   * the first one's Remove.
   */
  const [blocked, setBlocked] = useState<Record<string, string>>({});

  /** The client, with the delete leg observed for a `last-credential` refusal. */
  const watched = useMemo<PasskeysClient>(() => {
    const deletePasskey: PasskeysClient['deletePasskey'] = async (
      credentialId
    ) => {
      const outcome = await client.deletePasskey(credentialId);
      if (!outcome.ok && outcome.reason === 'last-credential') {
        setBlocked((current) => ({
          ...current,
          [credentialId]: refusalMessage(outcome),
        }));
      }
      return outcome;
    };
    const listPasskeys: PasskeysClient['listPasskeys'] = async () => {
      const outcome = await client.listPasskeys();
      if (outcome.ok) {
        setBlocked({});
      }
      return outcome;
    };
    return Object.assign(Object.create(client) as PasskeysClient, {
      deletePasskey,
      listPasskeys,
    });
  }, [client]);

  const panel = usePasskeyPanel({
    client: watched,
    messages: {
      created: (passkey) => `${passkey.name} is ready to sign in with.`,
      renamed: 'That passkey was renamed.',
      removed: 'That passkey was removed.',
    },
  });

  const list = panel.items ?? [];

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

      {panel.error !== null && (
        <div
          role="alert"
          className="mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded"
        >
          {panel.error}
        </div>
      )}
      {panel.notice !== null && (
        <div
          role="status"
          className="mb-4 p-3 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 rounded"
        >
          {panel.notice}
        </div>
      )}

      {panel.unavailable ? (
        <p
          data-testid="passkeys-unavailable"
          className="text-sm text-gray-600 dark:text-gray-400"
        >
          Passkeys are not switched on for this deployment.
        </p>
      ) : panel.items === null ? (
        <p className="text-sm text-gray-600 dark:text-gray-400">Loading...</p>
      ) : (
        <>
          {list.length === 0 ? (
            <p className="text-sm text-gray-600 dark:text-gray-400">
              No passkeys are set up on this account.
            </p>
          ) : (
            <ul className="space-y-3 mb-4">
              {list.map((passkey) => (
                <PasskeyRow
                  key={passkey.credentialId}
                  passkey={passkey}
                  busy={panel.busy}
                  renaming={panel.renaming === passkey.credentialId}
                  draft={panel.draftRename}
                  onDraftChange={panel.setDraftRename}
                  onStartRename={() => panel.startRename(passkey)}
                  onCancelRename={panel.cancelRename}
                  onCommitRename={() => void panel.commitRename()}
                  onDelete={() => void panel.remove(passkey.credentialId)}
                  blockedReason={blocked[passkey.credentialId] ?? null}
                />
              ))}
            </ul>
          )}

          {panel.adding ? (
            <form
              className="mt-4 space-y-3 p-4 border border-gray-200 dark:border-gray-700 rounded max-w-md"
              onSubmit={(e) => {
                e.preventDefault();
                void panel.commitCreate();
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
                value={panel.draftName}
                onChange={(e) => panel.setDraftName(e.target.value)}
                maxLength={64}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                disabled={panel.busy}
              />
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Something you will recognise in this list later. Your browser
                will ask for your device unlock next.
              </p>
              <div className="flex gap-3">
                <Button type="submit" variant="primary" disabled={panel.busy}>
                  {panel.busy ? 'Waiting for your device...' : 'Add passkey'}
                </Button>
                <Button
                  variant="outline"
                  onClick={panel.cancelCreate}
                  disabled={panel.busy}
                >
                  Cancel
                </Button>
              </div>
            </form>
          ) : (
            <Button
              variant="primary"
              onClick={() => {
                panel.startCreate();
                panel.setDraftName(defaultPasskeyName());
                panel.dismiss();
              }}
              disabled={panel.busy}
            >
              Add a passkey
            </Button>
          )}
        </>
      )}
    </div>
  );
};
