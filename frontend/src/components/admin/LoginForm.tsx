import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { PasskeySignInOutcome } from '@webbpulse/auth';

import { Button } from '../common';
import {
  API_BASE_URL,
  apiService,
  identityOriginFrom,
} from '../../services/api';
import { OAuthButtons } from './OAuthButtons';
import { PasskeySignInButton } from './PasskeySignInButton';
import { useOAuthProviders } from '../../hooks/useOAuthProviders';
import { usePasskeySignIn } from '../../hooks/usePasskeySignIn';

/**
 * The one sentence the reset request ever shows, whatever happened.
 *
 * Section 5.4 makes the request route answer identically for an address with
 * an account, one without, and one that just asked. Rendering a local sentence
 * that varied would hand back the distinction the route spends effort hiding,
 * so success and every refusal that is not a rate limit land here.
 */
const RESET_REQUESTED_MESSAGE =
  'If that address has an account, we sent a link to it.';

interface LoginFormProps {
  onLogin: (username: string, password: string) => Promise<void>;
  /**
   * Hands a finished passkey ceremony back to whoever owns the session.
   *
   * The outcome rather than a boolean, because a passkey sign-in has the same
   * two success shapes a password sign-in has: signed in outright, or an MFA
   * ticket to finish with. A user-verified passkey is two factors in one
   * gesture and lands on the first; one from an authenticator that did not
   * verify the user, on an account with TOTP, lands on the second. Only the
   * caller holds the ticket state, so only the caller can act on it.
   *
   * Absent in bearer mode, where there is no passkey affordance to press.
   */
  onPasskeySignIn?: (outcome: PasskeySignInOutcome) => void;
  loading: boolean;
  error: string | null;
  className?: string;
}

export const LoginForm: React.FC<LoginFormProps> = ({
  onLogin,
  onPasskeySignIn,
  loading,
  error,
  className = '',
}) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  /**
   * The identity client, or null in bearer mode.
   *
   * Read once at render rather than through a mode string, so the forgot
   * password affordance and the client that serves it cannot disagree: the
   * control appears exactly when there is something behind it.
   */
  const identity = apiService.getIdentityClient();

  /**
   * The providers this deployment configured, or an empty list.
   *
   * Empty in bearer mode, empty while the request is in flight, and empty on a
   * deployment that has no OAuth configured. `OAuthButtons` renders nothing for
   * an empty list, so all three cases produce the login page as it was.
   *
   * Takes the identity origin for the same reason `usePasskeySignIn` below
   * does: the discovery route is a sibling of `API_BASE_URL` at the origin
   * rather than a child of its `/api/v1` path.
   */
  const providers = useOAuthProviders(
    identity,
    identityOriginFrom(API_BASE_URL)
  );

  /**
   * Whether a passkey button belongs on this page, and whether this browser
   * can offer one through autofill.
   *
   * Both false in bearer mode, in a browser without WebAuthn, and on a backend
   * with passwordless sign-in switched off. See `hooks/usePasskeySignIn.ts`.
   */
  const passkeys = usePasskeySignIn(identity, identityOriginFrom(API_BASE_URL));

  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [passkeyError, setPasskeyError] = useState<string | null>(null);

  /**
   * The controller for a conditional ceremony waiting in the background.
   *
   * A conditional sign-in is a promise that sits unresolved until the user
   * picks a passkey out of the autofill dropdown, which may be never. It has
   * to be torn down when the user does something else instead, and the only
   * way to tear one down is the `AbortSignal` it was started with. A ref
   * rather than state, because aborting must not wait for a render and nothing
   * on screen depends on it.
   */
  const conditionalAbort = useRef<AbortController | null>(null);

  /** Tears down a pending conditional ceremony, if one is running. */
  const abortConditional = useCallback(() => {
    conditionalAbort.current?.abort();
    conditionalAbort.current = null;
  }, []);

  /**
   * Settles one finished ceremony.
   *
   * A cancellation is deliberately silent. The package reports a dismissed
   * browser prompt as `reason: 'cancelled'`, which is the same gesture as
   * pressing Cancel on an OAuth consent screen: the user changed their mind,
   * and rendering a red banner for that is telling them off for using the UI
   * correctly. Every other refusal renders the server's own sentence, for the
   * reason `SecuritySection` gives.
   */
  const settle = useCallback(
    (outcome: PasskeySignInOutcome) => {
      if (outcome.ok) {
        onPasskeySignIn?.(outcome);
        return;
      }
      if (outcome.reason === 'cancelled') {
        return;
      }
      if (outcome.reason === 'unavailable') {
        // The availability route said the capability was on and the ceremony
        // says it is not, which is a deployment that changed under the page.
        // Nothing the user can act on, so the affordance goes quiet rather
        // than shouting.
        return;
      }
      setPasskeyError(
        outcome.message.trim() !== ''
          ? outcome.message
          : 'That passkey could not be used to sign in. Try again.'
      );
    },
    [onPasskeySignIn]
  );

  /**
   * The explicit button press.
   *
   * Discoverable: no email is sent, so the authenticator offers whatever it
   * holds for this site. Any conditional ceremony is torn down first, because
   * two ceremonies cannot be outstanding at once and the modal one is what the
   * user just asked for.
   */
  const handlePasskeySignIn = useCallback(async () => {
    if (identity === null) return;
    abortConditional();
    setPasskeyBusy(true);
    setPasskeyError(null);
    try {
      settle(await identity.signInWithPasskey());
    } catch {
      // The package turns every refusal and the browser's own cancellation
      // into an outcome, so a throw here is a network failure, a 500, or a
      // session error. None of those is something a user can act on beyond
      // retrying.
      setPasskeyError('That sign-in could not be completed. Try again.');
    } finally {
      setPasskeyBusy(false);
    }
  }, [abortConditional, identity, settle]);

  /**
   * The autofill ceremony, started once when the browser supports it.
   *
   * `mediation: 'conditional'` puts the passkey in the same dropdown as a
   * saved username rather than a modal prompt, which is why the username input
   * below carries `autocomplete="username webauthn"`: without that token the
   * browser has nowhere to draw it.
   *
   * The cleanup aborts, which covers unmounting and the effect re-running.
   * Submitting the password form aborts too, in `handleSubmit`: leaving a
   * conditional ceremony outstanding while a password login completes is how a
   * page ends up with two sign-ins racing for the same session.
   */
  useEffect(() => {
    if (identity === null || !passkeys.offered || !passkeys.conditional) {
      return;
    }
    const controller = new AbortController();
    conditionalAbort.current = controller;

    void identity
      .signInWithPasskey({
        mediation: 'conditional',
        signal: controller.signal,
      })
      .then(outcome => {
        if (controller.signal.aborted) return;
        settle(outcome);
      })
      .catch(() => {
        // Same reasoning as the button handler, and quieter still: nothing
        // here was asked for out loud, so a background failure says nothing.
      });

    return () => {
      controller.abort();
      if (conditionalAbort.current === controller) {
        conditionalAbort.current = null;
      }
    };
  }, [identity, passkeys.offered, passkeys.conditional, settle]);

  const [resetOpen, setResetOpen] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [resetBusy, setResetBusy] = useState(false);
  const [resetNotice, setResetNotice] = useState<string | null>(null);

  const handleResetRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (identity === null) return;
    setResetBusy(true);
    try {
      const outcome = await identity.requestPasswordReset({
        email: resetEmail.trim(),
      });
      // A rate limit is the one case worth saying out loud: the neutral
      // sentence would promise a mail that is not coming.
      setResetNotice(
        !outcome.ok && outcome.reason === 'rate-limited'
          ? 'Too many requests. Please wait a while and try again.'
          : RESET_REQUESTED_MESSAGE
      );
    } catch {
      // A network failure or a 500. Still neutral: an error that only appeared
      // for addresses with accounts would be the same disclosure.
      setResetNotice(RESET_REQUESTED_MESSAGE);
    } finally {
      setResetBusy(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // The user chose the password instead. A conditional ceremony left running
    // would resolve later against a session that already exists, so it is torn
    // down before the password leaves. The abort surfaces as an `AbortError`,
    // which the package classifies as a cancellation and swallows.
    abortConditional();
    setPasskeyError(null);
    await onLogin(username, password);
  };

  return (
    <div
      className={`min-h-screen bg-gray-50 dark:bg-gray-900 py-12 ${className}`}
    >
      <div className="max-w-md mx-auto">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-8">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-6 text-center">
            Admin Login
          </h2>
          {error && (
            <div className="mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded">
              {error}
            </div>
          )}
          {passkeyError !== null && (
            <div
              role="alert"
              className="mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded"
            >
              {passkeyError}
            </div>
          )}
          <form onSubmit={e => void handleSubmit(e)} className="space-y-4">
            <div>
              <label
                htmlFor="username"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
              >
                Username
              </label>
              <input
                type="text"
                id="username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                // The `webauthn` token is what lets a conditional ceremony
                // draw a passkey into this field's autofill dropdown. Without
                // it the browser has nowhere to put one and the conditional
                // sign-in never becomes visible. Harmless when no ceremony is
                // running, and harmless in a browser that does not know it.
                autoComplete={
                  passkeys.conditional ? 'username webauthn' : 'username'
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                required
                disabled={loading}
              />
            </div>
            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
              >
                Password
              </label>
              <input
                type="password"
                id="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                required
                disabled={loading}
              />
            </div>
            <Button
              type="submit"
              variant="primary"
              className="w-full"
              disabled={loading}
            >
              {loading ? 'Logging in...' : 'Login'}
            </Button>
          </form>

          {identity !== null && (
            <OAuthButtons
              providers={providers}
              startUrl={provider =>
                identity.oauthStartUrl(provider, {
                  returnTo: window.location.pathname,
                })
              }
            />
          )}

          <PasskeySignInButton
            offered={passkeys.offered}
            busy={passkeyBusy}
            disabled={loading}
            onClick={() => void handlePasskeySignIn()}
          />
          {passkeys.offered && (
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400 text-center">
              A passkey uses your device unlock instead of a password. One that
              verified you counts as both factors, so it skips the code step.
            </p>
          )}

          {identity !== null && (
            <div className="mt-4">
              {resetOpen ? (
                <form
                  onSubmit={e => void handleResetRequest(e)}
                  className="space-y-3"
                >
                  <label
                    htmlFor="reset-email"
                    className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                  >
                    Email address
                  </label>
                  <input
                    type="email"
                    id="reset-email"
                    value={resetEmail}
                    onChange={e => setResetEmail(e.target.value)}
                    autoComplete="email"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                    required
                    disabled={resetBusy}
                  />
                  <Button
                    type="submit"
                    variant="secondary"
                    className="w-full"
                    disabled={resetBusy}
                  >
                    {resetBusy ? 'Sending...' : 'Send reset link'}
                  </Button>
                </form>
              ) : (
                <button
                  type="button"
                  onClick={() => setResetOpen(true)}
                  className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                >
                  Forgot password?
                </button>
              )}
              {resetNotice !== null && (
                <p
                  role="status"
                  className="mt-3 text-sm text-gray-600 dark:text-gray-400"
                >
                  {resetNotice}
                </p>
              )}
            </div>
          )}

          {/* Back to Home */}
          <div className="mt-6 text-center">
            <Link to="/">
              <Button variant="outline">← Back to Home</Button>
            </Link>
          </div>

          <div className="mt-4 text-sm text-gray-600 dark:text-gray-400 text-center">
            Enter your admin credentials
          </div>
        </div>
      </div>
    </div>
  );
};
