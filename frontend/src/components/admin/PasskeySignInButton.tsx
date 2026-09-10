import React from 'react';
import { FaFingerprint } from 'react-icons/fa';

/**
 * The "Sign in with a passkey" affordance under the password form.
 *
 * ## A button rather than a link
 *
 * The opposite of `OAuthButtons`, and for the opposite reason. An OAuth start
 * is a `302` to another origin, which is a navigation and so an anchor. A
 * passkey sign-in is two same-origin fetches with `navigator.credentials.get`
 * between them, which is a script call that must happen inside a user gesture.
 * That is a button.
 *
 * ## What it does not decide
 *
 * Nothing. Whether to render at all is the caller's answer, from
 * `usePasskeySignIn`: the browser has to support WebAuthn and the deployment
 * has to have passwordless sign-in switched on, and neither is something this
 * component can see. It renders nothing when `offered` is false, so a browser
 * without WebAuthn and a backend without the routes both produce the login
 * page exactly as it was.
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
