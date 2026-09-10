import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../common';
import { apiService } from '../../services/api';

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
  loading: boolean;
  error: string | null;
  className?: string;
}

export const LoginForm: React.FC<LoginFormProps> = ({
  onLogin,
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
