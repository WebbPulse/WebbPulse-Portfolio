import React, { useCallback, useEffect, useState } from 'react';
import type {
  OAuthLink,
  OAuthLinkOutcome,
  OAuthLinksOutcome,
  OAuthUnlinkOutcome,
} from '@webbpulse/auth';

import { Button } from '../common';
import {
  type OAuthProvider,
  providerLabel,
} from '../../services/oauthAvailability';

/**
 * The provider links on this account, with the link and unlink actions.
 *
 * The linked list is fetched; which providers could be attached is passed in, so
 * a linked but unconfigured provider can still be unlinked. `last-sign-in-method`
 * gets its own sentence because its remedy is an instruction.
 */

/** The subset of `AuthClient` this component calls. */
export interface OAuthLinksClient {
  listOAuthLinks: () => Promise<OAuthLinksOutcome>;
  linkOAuthProvider: (
    provider: string,
    options?: { returnTo?: string }
  ) => Promise<OAuthLinkOutcome>;
  unlinkOAuthProvider: (provider: string) => Promise<OAuthUnlinkOutcome>;
}

interface ConnectedAccountsProps {
  client: OAuthLinksClient;
  /**
   * The providers this deployment has configured, in backend order.
   *
   * Gates the attach buttons only, and carries a `display_name` to label them.
   * Linked rows go through `providerLabel`, since the links route sends only ids.
   */
  availableProviders: readonly OAuthProvider[];
  /** Where the link callback should land. Defaults to the current path. */
  returnTo?: string;
  /**
   * Sends the browser to the provider's authorization page.
   *
   * Injected so a test can observe the navigation rather than having jsdom
   * refuse it. The default is the real thing.
   */
  navigate?: (url: string) => void;
  className?: string;
}

/**
 * A sentence per refusal reason, used when the server sends an empty message.
 *
 * The server's own sentence is preferred everywhere, for the reason
 * `SecuritySection` gives: one written here would drift from the one the API
 * documents. These differ per reason because the remedy differs.
 */
const REASON_FALLBACKS: Record<string, string> = {
  'last-sign-in-method':
    'This is the only way to sign in to this account. Set a password first, then disconnect it.',
  'not-linked':
    'That account is not connected any more. The list has been reloaded.',
  'already-linked':
    'That provider account is already connected to an account. Sign in with it instead.',
  'provider-unavailable':
    'That provider is not available on this deployment right now.',
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

/** One attached provider, with its dates and the disconnect action. */
const LinkRow: React.FC<{
  link: OAuthLink;
  busy: boolean;
  onUnlink: () => void;
}> = ({ link, busy, onUnlink }) => {
  const linkedAt = formatInstant(link.linkedAt);
  const lastLoginAt = formatInstant(link.lastLoginAt);

  return (
    <li
      data-testid={`oauth-link-${link.provider}`}
      className="flex flex-wrap items-center justify-between gap-3 p-4 border border-gray-200 dark:border-gray-700 rounded"
    >
      <div>
        <p className="text-base font-medium text-gray-900 dark:text-white">
          {providerLabel(link.provider)}
        </p>
        {link.email !== '' && (
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {link.email}
            {!link.emailVerified && ' (unverified at the provider)'}
          </p>
        )}
        <p className="text-sm text-gray-500 dark:text-gray-500">
          {linkedAt === null ? 'Connected' : `Connected ${linkedAt}`}
          {lastLoginAt !== null && `, last used ${lastLoginAt}`}
        </p>
      </div>
      <Button variant="outline" size="sm" onClick={onUnlink} disabled={busy}>
        Disconnect
      </Button>
    </li>
  );
};

/** Renders the linked providers and the link and unlink controls. */
export const ConnectedAccounts: React.FC<ConnectedAccountsProps> = ({
  client,
  availableProviders,
  returnTo,
  navigate,
  className = '',
}) => {
  const [links, setLinks] = useState<OAuthLink[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  /**
   * Reloads the list.
   *
   * Also the callback the OAuth `?oauth_linked=1` landing runs, which is why
   * it is exposed through the window hook below rather than only called on
   * mount.
   */
  const reload = useCallback(async () => {
    try {
      const outcome = await client.listOAuthLinks();
      if (outcome.ok) {
        setLinks(outcome.links);
        return;
      }
      setLinks([]);
      setError(refusalMessage(outcome));
    } catch {
      setLinks([]);
      setError('Connected accounts could not be loaded. Try again.');
    }
  }, [client]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleLink = useCallback(
    async (provider: string) => {
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const outcome = await client.linkOAuthProvider(provider, {
          returnTo: returnTo ?? window.location.pathname,
        });
        if (outcome.ok) {
          (navigate ?? ((url: string) => window.location.assign(url)))(
            outcome.authorizationUrl
          );
          return;
        }
        setError(refusalMessage(outcome));
      } catch {
        setError('That provider could not be connected. Try again.');
      } finally {
        setBusy(false);
      }
    },
    [client, navigate, returnTo]
  );

  const handleUnlink = useCallback(
    async (provider: string) => {
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const outcome = await client.unlinkOAuthProvider(provider);
        if (outcome.ok) {
          setNotice(`${providerLabel(provider)} is no longer connected.`);
          await reload();
          return;
        }
        setError(refusalMessage(outcome));
        if (outcome.reason === 'not-linked') {
          await reload();
        }
      } catch {
        setError('That provider could not be disconnected. Try again.');
      } finally {
        setBusy(false);
      }
    },
    [client, reload]
  );

  const linked = links ?? [];
  const linkedProviders = new Set(linked.map(link => link.provider));
  const connectable = availableProviders.filter(
    provider => !linkedProviders.has(provider.id)
  );

  return (
    <div className={className} data-testid="connected-accounts">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
        Connected accounts
      </h3>
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
        Providers you can sign in to this panel with, alongside your password.
        Disconnecting the only remaining way in is refused, so set a password
        before removing the last one.
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

      {links === null ? (
        <p className="text-sm text-gray-600 dark:text-gray-400">Loading...</p>
      ) : linked.length === 0 ? (
        <p className="text-sm text-gray-600 dark:text-gray-400">
          No providers are connected to this account.
        </p>
      ) : (
        <ul className="space-y-3 mb-4">
          {linked.map(link => (
            <LinkRow
              key={link.provider}
              link={link}
              busy={busy}
              onUnlink={() => void handleUnlink(link.provider)}
            />
          ))}
        </ul>
      )}

      {connectable.length > 0 && (
        <div className="flex flex-wrap gap-3 mt-4">
          {connectable.map(({ id, display_name: label }) => (
            <Button
              key={id}
              variant="outline"
              onClick={() => void handleLink(id)}
              disabled={busy}
            >
              Connect {label}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
};
