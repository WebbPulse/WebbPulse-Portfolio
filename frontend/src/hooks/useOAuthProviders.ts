/**
 * The OAuth providers this deployment offers, fetched once per page load.
 *
 * One request for the whole list. The list starts empty and fills in after a
 * round trip, so no disabled buttons are rendered first.
 */
import { useEffect, useState } from 'react';
import type { AuthClient } from '@webbpulse/auth';
import {
  identityUrl,
  oauthProviders,
  OAUTH_PROVIDERS_PATH,
  type OAuthProviderInfo,
} from '@webbpulse/discovery';

/**
 * The providers to offer, in the order the backend listed them.
 *
 * A null client is bearer mode, where no request is made. `identityOrigin` is
 * passed in so this hook needs no knowledge of how the bundle is configured.
 */
export function useOAuthProviders(
  client: AuthClient<unknown> | null,
  identityOrigin: string,
  fetchImpl?: typeof fetch
): OAuthProviderInfo[] {
  const [available, setAvailable] = useState<OAuthProviderInfo[]>([]);

  useEffect(() => {
    if (client === null || typeof client.oauthStartUrl !== 'function') {
      setAvailable([]);
      return;
    }
    let live = true;

    void oauthProviders(
      identityUrl(identityOrigin, OAUTH_PROVIDERS_PATH),
      fetchImpl
    ).then((providers) => {
      if (!live) return;
      setAvailable(providers);
    });

    return () => {
      live = false;
    };
  }, [client, identityOrigin, fetchImpl]);

  return available;
}
