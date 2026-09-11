import React from 'react';
import { FaGithub, FaGoogle } from 'react-icons/fa';
import { GITHUB_PROVIDER, GOOGLE_PROVIDER } from '@webbpulse/auth';

import type { OAuthProvider } from '../../services/oauthAvailability';

/**
 * The "Sign in with ..." row under the password form.
 *
 * Anchors rather than buttons, because a start is a 302 a fetch cannot follow.
 * Renders nothing for an empty list, and labels come from the backend's
 * `display_name` so a new provider needs no change here.
 */

/** The mark for each provider, keyed by the package's own constants. */
const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  [GOOGLE_PROVIDER]: FaGoogle,
  [GITHUB_PROVIDER]: FaGithub,
};

interface OAuthButtonsProps {
  /** The providers to offer, in backend order. Empty renders nothing at all. */
  providers: readonly OAuthProvider[];
  /**
   * Builds the start URL for one provider.
   *
   * `oauthStartUrl` bound with the caller's `returnTo`, passed in so this component
   * needs no knowledge of the auth package.
   */
  startUrl: (provider: string) => string;
  className?: string;
}

/** Renders one sign in link per configured provider. */
export const OAuthButtons: React.FC<OAuthButtonsProps> = ({
  providers,
  startUrl,
  className = '',
}) => {
  if (providers.length === 0) {
    return null;
  }

  return (
    <div className={`mt-6 ${className}`}>
      <div className="relative">
        <div className="absolute inset-0 flex items-center" aria-hidden="true">
          <div className="w-full border-t border-gray-300 dark:border-gray-600" />
        </div>
        <div className="relative flex justify-center">
          <span className="px-2 bg-white dark:bg-gray-800 text-sm text-gray-500 dark:text-gray-400">
            or
          </span>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {providers.map(({ id, display_name: label }) => {
          const Icon = ICONS[id];
          return (
            <a
              key={id}
              href={startUrl(id)}
              data-testid={`oauth-start-${id}`}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-base font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 transition-colors"
            >
              {Icon !== undefined && <Icon className="w-5 h-5" />}
              Sign in with {label}
            </a>
          );
        })}
      </div>
    </div>
  );
};
