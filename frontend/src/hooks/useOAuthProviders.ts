/**
 * The OAuth providers this deployment offers, fetched once per page load.
 *
 * One request for the whole list, not one per provider. Until webbpulse-python
 * 0.16.0 there was no discovery route, so this hook asked
 * `services/oauthAvailability.ts` to probe each provider's start route and kept
 * the ones that answered "available". That spent the start route's own rate
 * limit budget on page loads and could not tell an unconfigured provider from a
 * configured one that was briefly failing. `GET /api/auth/oauth/providers`
 * answers the question directly, and that file has the full reasoning.
 *
 * The list starts empty and fills in after a round trip, which is why the
 * sign-in page renders nothing at all until it does rather than rendering a row
 * of disabled buttons that then disappear.
 */
import { useEffect, useState } from 'react';
import type { AuthClient } from '@webbpulse/auth';

import {
  type OAuthProvider,
  oauthProviders,
} from '../services/oauthAvailability';

/**
 * The providers to offer, in the order the backend listed them.
 *
 * `client` being null is bearer mode, where there are no identity routes at all
 * and no request is made.
 *
 * `identityOrigin` is the origin the identity routes are served from, the same
 * value `usePasskeySignIn` takes and for the same reason: `API_BASE_URL`
 * carries the `/api/v1` path that the content routes live under, and the
 * identity routes are siblings of it at the origin rather than children of it.
 * Passed in rather than read here so this hook needs no knowledge of how the
 * bundle is configured.
 */
export function useOAuthProviders(
  client: AuthClient<unknown> | null,
  identityOrigin: string
): OAuthProvider[] {
  const [available, setAvailable] = useState<OAuthProvider[]>([]);

  useEffect(() => {
    // `oauthStartUrl` arrived in `@webbpulse/auth` 0.7.0. Checking for it
    // rather than assuming it keeps this hook safe against an older client
    // reaching it, which is otherwise a thrown TypeError inside an effect and
    // takes the whole sign-in page down rather than hiding two buttons. The
    // fetch below does not use the client, but the buttons this list feeds do:
    // rendering them against a client that cannot build a start URL would move
    // the same failure one component along.
    if (client === null || typeof client.oauthStartUrl !== 'function') {
      setAvailable([]);
      return;
    }
    // Guards the state write against a client swap or an unmount between the
    // request starting and finishing. Without it React logs an update on an
    // unmounted component, and worse, a stale answer could overwrite a fresh
    // one.
    let live = true;

    void oauthProviders(identityOrigin).then(providers => {
      if (!live) return;
      setAvailable(providers);
    });

    return () => {
      live = false;
    };
  }, [client, identityOrigin]);

  return available;
}
