import React from 'react';
import { FaGithub, FaGoogle } from 'react-icons/fa';
import { GITHUB_PROVIDER, GOOGLE_PROVIDER } from '@webbpulse/auth';

import { providerLabel } from '../../services/oauthAvailability';

/**
 * The "Sign in with ..." row under the password form.
 *
 * ## Links rather than buttons
 *
 * `GET /api/auth/oauth/{provider}/start` answers `302` to the provider, which
 * is a browser navigation and not something a `fetch` can follow. The package
 * says as much by handing back a URL from `oauthStartUrl` rather than a
 * promise. An anchor is the right element for that: it is announced as a link,
 * it is middle-clickable, and it needs no click handler to work. `startOAuth`
 * exists for a caller that wants the navigation without the anchor, and this
 * is not that caller.
 *
 * ## Which providers appear
 *
 * Whatever the caller passes, which is the probed set from
 * `useOAuthProviders`. This component renders nothing for an empty list rather
 * than an empty divider, so a deployment with no OAuth configured shows a
 * login page identical to the one before this feature existed.
 */

/** The mark for each provider, keyed by the package's own constants. */
const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  [GOOGLE_PROVIDER]: FaGoogle,
  [GITHUB_PROVIDER]: FaGithub,
};

interface OAuthButtonsProps {
  /** The providers to offer. Empty renders nothing at all. */
  providers: readonly string[];
  /**
   * Builds the start URL for one provider.
   *
   * `AuthClient.oauthStartUrl` bound with whatever `returnTo` the caller wants
   * the callback to land on. Passed in rather than taking the client, so this
   * component needs no knowledge of the auth package beyond the two provider
   * names it draws icons for.
   */
  startUrl: (provider: string) => string;
  className?: string;
}

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
        {providers.map(provider => {
          const Icon = ICONS[provider];
          const label = providerLabel(provider);
          return (
            <a
              key={provider}
              href={startUrl(provider)}
              data-testid={`oauth-start-${provider}`}
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
