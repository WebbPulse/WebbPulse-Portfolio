import React, { useState } from 'react';
import { Button } from '../common';

/**
 * The second leg of an identity login, when the account has a TOTP factor.
 *
 * Deliberately small. The first leg already answered with a ticket, so all
 * this collects is the six digit code and hands it back; the ticket itself is
 * held by the panel and never reaches this component, which keeps a single
 * use credential out of a form's state.
 *
 * Reached only in identity mode. The bearer login route has no second leg, so
 * nothing renders this there.
 */
interface TotpFormProps {
  onSubmit: (code: string) => Promise<void>;
  onCancel: () => void;
  loading: boolean;
  error: string | null;
  className?: string;
}

export const TotpForm: React.FC<TotpFormProps> = ({
  onSubmit,
  onCancel,
  loading,
  error,
  className = '',
}) => {
  const [code, setCode] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmit(code.trim());
  };

  return (
    <div
      className={`min-h-screen bg-gray-50 dark:bg-gray-900 py-12 ${className}`}
    >
      <div className="max-w-md mx-auto">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-8">
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2 text-center">
            Two Factor Code
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-6 text-center">
            Enter the code from your authenticator app.
          </p>
          {error && (
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
                htmlFor="totp-code"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
              >
                Authentication code
              </label>
              <input
                type="text"
                id="totp-code"
                value={code}
                onChange={e => setCode(e.target.value)}
                // A one time code, so the browser can offer it from the
                // platform's own autofill rather than the user retyping it.
                autoComplete="one-time-code"
                inputMode="numeric"
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
              {loading ? 'Verifying...' : 'Verify'}
            </Button>
          </form>

          <div className="mt-6 text-center">
            <Button variant="outline" onClick={onCancel} disabled={loading}>
              Back to sign in
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
