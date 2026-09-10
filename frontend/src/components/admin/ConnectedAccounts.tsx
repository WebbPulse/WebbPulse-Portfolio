import React, { useCallback, useEffect, useState } from 'react';
import type {
  OAuthLink,
  OAuthLinkOutcome,
  OAuthLinksOutcome,
  OAuthUnlinkOutcome,
} from '@webbpulse/auth';

import { Button } from '../common';
import { providerLabel } from '../../services/oauthAvailability';

/**
 * The provider links on this account, with the link and unlink actions.
 *
 * ## Why the list is loaded and the availability is passed in
 *
 * These are two different questions. `listOAuthLinks` answers "what is
 * attached to this account", which is a route and a fetch. "Which providers
 * could be attached" has no route at all in webbpulse-python 0.14.0, so it is
 * probed once per page load and handed down. Keeping them apart matters for
 * one case: a provider that is linked but no longer configured still appears
 * in the list, and it must, because the user has to be able to unlink it.
 * Only the *attach* affordance is gated on availability.
 *
 * ## The refusal that needs its own sentence
 *
 * `last-sign-in-method` is the one refusal in the package whose remedy is a
 * specific instruction rather than "try again". The server counts what would
 * be left, and refuses when nothing would be, because an account with no way
 * in is not recoverable through any path this design has. Its own sentence is
 * rendered, and a fallback is written here for a server that sends an empty
 * message, because a generic failure toast would leave the user pressing the
 * same button.
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
   * The providers this deployment has configured.
   *
   * Gates the attach buttons only. See the note above for why unlinking is not
   * gated on it.
   */
  availableProviders: readonly string[];
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
      // A network failure, a 500, or a 401 the transport could not repair. The
      // last of those is the session ending, which `onSessionEnded` handles
      // elsewhere; there is nothing useful to say here beyond that the list is
      // not showing.
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
          // The page is leaving. No state is cleared first, because nothing
          // here survives the navigation.
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
          // A stale list: it was removed in another tab, or the button was
          // pressed twice. Reloading is the remedy the package names.
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
    provider => !linkedProviders.has(provider)
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
          {connectable.map(provider => (
            <Button
              key={provider}
              variant="outline"
              onClick={() => void handleLink(provider)}
              disabled={busy}
            >
              Connect {providerLabel(provider)}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
};
