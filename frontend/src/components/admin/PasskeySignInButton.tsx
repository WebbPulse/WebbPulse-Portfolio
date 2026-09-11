import React from 'react';
import { FaFingerprint } from 'react-icons/fa';

/**
 * The "Sign in with a passkey" affordance under the password form.
 *
 * A button rather than a link, because the ceremony is a script call inside a
 * user gesture. Renders nothing when `offered` is false; the caller decides.
 */

interface PasskeySignInButtonProps {
  /** Whether the affordance is offered at all. False renders nothing. */
  offered: boolean;
  /** Whether a ceremony is already running. */
  busy: boolean;
  /** Whether the password form is mid-submit, which disables this too. */
  disabled?: boolean;
  onClick: () => void;
  className?: string;
}

/** Renders the passkey sign in button, or nothing when it is not offered. */
export const PasskeySignInButton: React.FC<PasskeySignInButtonProps> = ({
  offered,
  busy,
  disabled = false,
  onClick,
  className = '',
}) => {
  if (!offered) {
    return null;
  }

  return (
    <div className={`mt-4 ${className}`}>
      <button
        type="button"
        data-testid="passkey-sign-in"
        onClick={onClick}
        disabled={busy || disabled}
        className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-base font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-60 transition-colors"
      >
        <FaFingerprint className="w-5 h-5" />
        {busy ? 'Waiting for your passkey...' : 'Sign in with a passkey'}
      </button>
    </div>
  );
};
