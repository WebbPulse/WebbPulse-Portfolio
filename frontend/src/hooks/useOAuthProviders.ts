/**
 * The OAuth providers this deployment has configured, probed once per page.
 *
 * Returns only the providers that answered "available". A provider whose probe
 * failed is left out rather than rendered as a broken button: the whole point
 * of the gate is that a user never sees "Sign in with Google" on a backend
 * where pressing it 404s.
 *
 * The list starts empty and fills in after a round trip, which is why the
 * login page renders nothing at all until it does rather than rendering a row
 * of disabled buttons that then disappear. See `services/oauthAvailability.ts`
 * for why a probe is needed and what a discovery endpoint would replace.
 */
import { useEffect, useState } from 'react';
import type { AuthClient } from '@webbpulse/auth';

import {
  OAUTH_PROVIDERS,
  providerAvailability,
} from '../services/oauthAvailability';

/**
 * The available providers, in {@link OAUTH_PROVIDERS} order.
 *
 * `client` being null is bearer mode, where there are no identity routes at
 * all and no probe is made.
 */
export function useOAuthProviders(
  client: AuthClient<unknown> | null
): string[] {
  const [available, setAvailable] = useState<string[]>([]);

  useEffect(() => {
    // `oauthStartUrl` arrived in `@webbpulse/auth` 0.7.0. Checking for it
    // rather than assuming it keeps this hook safe against an older client
    // reaching it, which is otherwise a thrown TypeError inside an effect and
    // takes the whole login page down rather than hiding two buttons.
    if (client === null || typeof client.oauthStartUrl !== 'function') {
      setAvailable([]);
      return;
    }
    // Guards the state write against a client swap or an unmount between the
    // probe starting and finishing. Without it React logs an update on an
    // unmounted component, and worse, a stale answer could overwrite a fresh
    // one.
    let live = true;

    void Promise.all(
      OAUTH_PROVIDERS.map(async provider => {
        const state = await providerAvailability(
          client.oauthStartUrl(provider)
        );
        return { provider, ok: state === 'available' };
      })
    ).then(results => {
      if (!live) return;
      setAvailable(results.filter(r => r.ok).map(r => r.provider));
    });

    return () => {
      live = false;
    };
  }, [client]);

  return available;
}
