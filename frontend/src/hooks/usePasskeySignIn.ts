/**
 * Whether to offer a "Sign in with a passkey" button, and whether the browser
 * can put a passkey in its autofill dropdown.
 *
 * Three separate questions have to all answer yes before the button appears,
 * and they fail in different ways:
 *
 * 1. **Is this identity mode?** Bearer mode has no `/api/auth` routes at all.
 *    A null client is the answer, and no probe is made.
 * 2. **Can this browser do WebAuthn?** `passkeysSupported()` reads
 *    `PublicKeyCredential` off the global, which is present exactly when the
 *    API is. False in a browser served over plain HTTP, because WebAuthn is a
 *    secure-context API, and false in jsdom. A button that throws when pressed
 *    is worse than no button.
 * 3. **Does this deployment have passwordless sign-in on?** Read from
 *    `GET /api/auth/passkeys/availability`, which webbpulse-python 0.17.0
 *    added for exactly this. Until that release there was no discovery route
 *    and this question was answered by probing
 *    `POST /api/auth/login/passkey/options`, which spent a rate limit slot and
 *    wrote a challenge row per sign-in page load. See
 *    `services/passkeyAvailability.ts`.
 *
 * Conditional mediation is a fourth question and a separate capability: a
 * browser can do WebAuthn without it. It is asked only when the first three
 * said yes, since there is no point starting an autofill ceremony against a
 * deployment that has the route switched off.
 *
 * The hook starts with everything false and fills in after a round trip, which
 * is why the login page renders no passkey affordance until it does rather
 * than rendering one that then disappears. The round trip is now a cached GET
 * rather than a rate limited POST, so the wait is usually the browser's own
 * HTTP cache answering.
 *
 * This hook reads `passwordless` and not `enabled`. They are different
 * questions and a deployment can answer yes to the first and no to the second:
 * with `enabled` true and `passwordless` false a passkey is a managed
 * credential and a second factor but not an entry point, so the settings panel
 * offers to add one and this button must not appear. The package gates
 * `passwordless` on `enabled` in the route itself, so reading it alone is
 * safe.
 */
import { useEffect, useState } from 'react';
import type { AuthClient } from '@webbpulse/auth';
import {
  conditionalMediationAvailable,
  passkeysSupported,
} from '@webbpulse/auth';

import { passkeyLoginOffered } from '../services/passkeyAvailability';

/** What the login page needs to know before drawing anything. */
export interface PasskeySignInSupport {
  /** Whether to render the button at all. All three questions said yes. */
  offered: boolean;
  /** Whether to start a conditional ceremony against the username field. */
  conditional: boolean;
}

/**
 * The passkey affordances this browser and this deployment can support.
 *
 * `identityOrigin` is the origin the identity routes are mounted on, which is
 * the API origin rather than this application's `/api/v1` base. It is passed
 * in rather than read off the client because `AuthClient` keeps its own client
 * private and exposes no equivalent of `oauthStartUrl` for the passkey routes.
 * It is passed as an origin rather than a full URL, the way `useOAuthProviders`
 * takes one: the service owns the path, so a route the package renames is one
 * edit in one file.
 */
export function usePasskeySignIn(
  client: AuthClient<unknown> | null,
  identityOrigin: string
): PasskeySignInSupport {
  const [support, setSupport] = useState<PasskeySignInSupport>({
    offered: false,
    conditional: false,
  });

  useEffect(() => {
    // `signInWithPasskey` arrived in `@webbpulse/auth` 0.8.0. Checking for it
    // rather than assuming it keeps this hook safe against an older client
    // reaching it, which is otherwise a thrown TypeError inside an effect and
    // takes the whole login page down rather than hiding one button.
    if (
      client === null ||
      typeof client.signInWithPasskey !== 'function' ||
      !passkeysSupported()
    ) {
      setSupport({ offered: false, conditional: false });
      return;
    }
    // Guards the state write against a client swap or an unmount between the
    // probe starting and finishing.
    let live = true;

    void (async () => {
      const offered = await passkeyLoginOffered(identityOrigin);
      if (!live) return;
      if (!offered) {
        setSupport({ offered: false, conditional: false });
        return;
      }
      const conditional = await conditionalMediationAvailable();
      if (!live) return;
      setSupport({ offered: true, conditional });
    })();

    return () => {
      live = false;
    };
  }, [client, identityOrigin]);

  return support;
}
