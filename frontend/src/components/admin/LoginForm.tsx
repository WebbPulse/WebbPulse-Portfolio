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
 * The route answers identically for every address, so a varying local sentence
 * would hand back the distinction it hides.
 */
const RESET_REQUESTED_MESSAGE =
  'If that address has an account, we sent a link to it.';

interface LoginFormProps {
  onLogin: (username: string, password: string) => Promise<void>;
  /**
   * Hands a finished passkey ceremony back to whoever owns the session.
   *
   * The outcome rather than a boolean, since a passkey sign-in can land signed in
   * or on an MFA ticket. Absent in bearer mode.
   */
  onPasskeySignIn?: (outcome: PasskeySignInOutcome) => void;
  loading: boolean;
  error: string | null;
  className?: string;
}

/** The sign in form, with the OAuth and passkey affordances when offered. */
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
   * Read at render so the forgot password control appears exactly when something
   * is behind it.
   */
  const identity = apiService.getIdentityClient();

  /**
   * The providers this deployment configured, or an empty list.
   *
   * Empty in bearer mode, in flight, and with no OAuth configured; `OAuthButtons`
   * renders nothing for all three.
   */
  const providers = useOAuthProviders(
    identity,
    identityOriginFrom(API_BASE_URL)
  );

  /**
   * Whether a passkey button belongs on this page, and whether this browser can
   * offer one through autofill.
   *
   * Both false in bearer mode, without WebAuthn, or with passwordless switched off.
   */
  const passkeys = usePasskeySignIn(identity, identityOriginFrom(API_BASE_URL));

  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [passkeyError, setPasskeyError] = useState<string | null>(null);

  /**
   * The controller for a conditional ceremony waiting in the background.
   *
   * A ref rather than state, because aborting must not wait for a render.
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
   * A cancellation is silent, since a dismissed prompt is the user changing their
   * mind. Every other refusal renders the server's own sentence.
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
   * Discoverable, and any conditional ceremony is torn down first because two
   * cannot be outstanding at once.
   */
  const handlePasskeySignIn = useCallback(async () => {
    if (identity === null) return;
    abortConditional();
    setPasskeyBusy(true);
    setPasskeyError(null);
    try {
      settle(await identity.signInWithPasskey());
    } catch {
      setPasskeyError('That sign-in could not be completed. Try again.');
    } finally {
      setPasskeyBusy(false);
    }
  }, [abortConditional, identity, settle]);

  /**
   * The autofill ceremony, started once when the browser supports it.
   *
   * `mediation: 'conditional'` needs the username input's `webauthn` token. The
   * cleanup aborts, as does submitting the password form.
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
      .then((outcome) => {
        if (controller.signal.aborted) return;
        settle(outcome);
      })
      .catch(() => {});

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
      setResetNotice(
        !outcome.ok && outcome.reason === 'rate-limited'
          ? 'Too many requests. Please wait a while and try again.'
          : RESET_REQUESTED_MESSAGE
      );
    } catch {
      setResetNotice(RESET_REQUESTED_MESSAGE);
    } finally {
      setResetBusy(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
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
          <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
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
                onChange={(e) => setUsername(e.target.value)}
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
                onChange={(e) => setPassword(e.target.value)}
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
              startUrl={(provider) =>
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
                  onSubmit={(e) => void handleResetRequest(e)}
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
                    onChange={(e) => setResetEmail(e.target.value)}
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
