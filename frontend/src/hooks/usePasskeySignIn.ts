/**
 * Whether to offer a passkey sign-in button, and whether the browser can put a
 * passkey in its autofill dropdown.
 *
 * Identity mode, WebAuthn support and the deployment's `passwordless` flag must
 * all say yes; conditional mediation is asked only after they do.
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
 * `identityOrigin` is the origin the identity routes are mounted on, passed in
 * so the service owns the path.
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
    if (
      client === null ||
      typeof client.signInWithPasskey !== 'function' ||
      !passkeysSupported()
    ) {
      setSupport({ offered: false, conditional: false });
      return;
    }
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
