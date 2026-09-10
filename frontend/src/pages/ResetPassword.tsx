import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { RESET_PASSWORD_PATH, readLinkToken } from '@webbpulse/auth';
import { Button } from '../components/common';
import { apiService } from '../services/api';

/**
 * The page a password reset link from the backend lands on.
 *
 * The mailed URL is `<frontend base>/reset-password?token=...`, and
 * `RESET_PASSWORD_PATH` is the literal both sides agree on. Note that this is
 * the SPA page, not the API route: the API confirms at
 * `/api/auth/reset/confirm`, which this page calls once the user has chosen a
 * password.
 *
 * Unlike verification, nothing happens on mount. The token is read up front so
 * a broken link fails immediately rather than after the user has typed a
 * password, but it is only spent when the form is submitted.
 *
 * On success every session for the account is gone, this browser's included,
 * which is why the end of the flow is the sign in form rather than the admin
 * panel: the reset is the remedy for a compromise, so the backend revokes
 * every refresh family and the user signs in again with the new password.
 */

/** How long the success notice sits before the page moves to sign in. */
const REDIRECT_DELAY_MS = 1500;

/** The sentence for each refusal the confirm route can answer with. */
function describeRefusal(reason: string, message: string): string {
  switch (reason) {
    case 'invalid-link':
      return 'This link is no longer valid. It may have expired or already been used. Request a new one from the sign in page.';
    case 'password-rejected':
      // The server names what was wrong with the password, and its own
      // sentence is more useful than a generic one. The link is spent either
      // way, so the remedy is a new link and a different password.
      return `${message} This link is now used, so request a new one and choose a different password.`;
    case 'rate-limited':
      return 'Too many attempts. Please wait a while and try again.';
    case 'unavailable':
      return 'Password reset is temporarily unavailable. Please try again later.';
    default:
      return 'We could not reset your password. Please try again later.';
  }
}

export const ResetPassword: React.FC = () => {
  const navigate = useNavigate();
  const identity = apiService.getIdentityClient();

  // Read once at first render. `expectedPath` keeps a verification token that
  // was pasted here from being presented to the reset endpoint.
  const [token] = useState<string | null>(() =>
    identity === null
      ? null
      : readLinkToken({ expectedPath: RESET_PASSWORD_PATH })
  );

  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (identity === null || token === null) return;

    // Checked here rather than by the server, which never sees the second
    // field: a mistyped confirmation must not spend the single use token.
    if (password !== confirmation) {
      setError('The two passwords do not match.');
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const outcome = await identity.confirmPasswordReset({
        token,
        newPassword: password,
      });
      if (outcome.ok) {
        setDone(true);
        globalThis.setTimeout(() => {
          void navigate('/admin');
        }, REDIRECT_DELAY_MS);
        return;
      }
      setError(describeRefusal(outcome.reason, outcome.message));
    } catch {
      setError('We could not reset your password. Please try again later.');
    } finally {
      setBusy(false);
    }
  };

  const shell = (children: React.ReactNode) => (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-12">
      <div className="max-w-md mx-auto">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-8">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6 text-center">
            Choose a New Password
          </h1>
          {children}
        </div>
      </div>
    </div>
  );

  if (identity === null) {
    return shell(
      <div role="alert" className="text-center">
        <p className="text-gray-600 dark:text-gray-400 mb-6">
          Password reset is not enabled for this site.
        </p>
        <Link to="/">
          <Button variant="outline">Back to home</Button>
        </Link>
      </div>
    );
  }

  if (token === null) {
    return shell(
      <div role="alert" className="text-center">
        <p className="font-medium text-gray-900 dark:text-white mb-2">
          This link is missing its token
        </p>
        <p className="text-gray-600 dark:text-gray-400 mb-6">
          Open the link from your email again, or request a new one from the
          sign in page.
        </p>
        <Link to="/admin">
          <Button variant="outline">Back to sign in</Button>
        </Link>
      </div>
    );
  }

  if (done) {
    return shell(
      <div role="status" className="text-center">
        <p className="text-green-700 dark:text-green-400 mb-6">
          Your password is updated. Sign in with your new password.
        </p>
        <Link to="/admin">
          <Button variant="primary">Go to sign in</Button>
        </Link>
      </div>
    );
  }

  return shell(
    <>
      {error !== null && (
        <div
          role="alert"
          className="mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded"
        >
          {error}
        </div>
      )}
      <form onSubmit={e => void handleSubmit(e)} className="space-y-4">
        <div>
          <label
            htmlFor="new-password"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            New password
          </label>
          <input
            type="password"
            id="new-password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            autoComplete="new-password"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
            required
            disabled={busy}
          />
        </div>
        <div>
          <label
            htmlFor="confirm-password"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            Confirm new password
          </label>
          <input
            type="password"
            id="confirm-password"
            value={confirmation}
            onChange={e => setConfirmation(e.target.value)}
            autoComplete="new-password"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
            required
            disabled={busy}
          />
        </div>
        <Button
          type="submit"
          variant="primary"
          className="w-full"
          disabled={busy}
        >
          {busy ? 'Saving...' : 'Set new password'}
        </Button>
      </form>

      <div className="mt-6 text-center">
        <Link to="/admin">
          <Button variant="outline">Back to sign in</Button>
        </Link>
      </div>
    </>
  );
};

export default ResetPassword;
