import React, { useCallback, useState } from 'react';
import type {
  RecoveryCodesOutcome,
  TotpActivationOutcome,
  TotpDisableOutcome,
  TotpEnrolmentOutcome,
} from '@webbpulse/auth';

import { qrCodeSvgPath } from '@webbpulse/qrcode';
import type { OAuthProviderInfo } from '@webbpulse/discovery';

import { Button } from '../common';
import { ConnectedAccounts, type OAuthLinksClient } from './ConnectedAccounts';
import { PasskeysPanel, type PasskeysClient } from './PasskeysPanel';

/**
 * The admin panel's second factor management, in identity mode.
 *
 * No route reports whether TOTP is on, so enrolment state is tracked per session
 * and starts `unknown`. The seed and the recovery codes are each shown once,
 * so the codes sit behind an explicit confirmation.
 */

/** What this session knows about the account's factor. See the note above. */
type FactorState = 'unknown' | 'enabled' | 'disabled';

/** Which step of the enrolment sequence is on screen. */
type EnrolStep =
  | { step: 'idle' }
  | { step: 'scanning'; secret: string; provisioningUri: string }
  | { step: 'codes'; codes: string[] };

/**
 * The subset of `AuthClient` this component calls.
 *
 * Function properties rather than method shorthand, so a reference in a test is
 * not an `unbound-method` finding.
 */
export interface SecurityClient {
  enrolTotp: () => Promise<TotpEnrolmentOutcome>;
  activateTotp: (input: { code: string }) => Promise<TotpActivationOutcome>;
  disableTotp: (input: { code: string }) => Promise<TotpDisableOutcome>;
  regenerateRecoveryCodes: (input: {
    code: string;
  }) => Promise<RecoveryCodesOutcome>;
}

interface SecuritySectionProps {
  client: SecurityClient;
  /**
   * The three OAuth link routes, or null where they are not offered.
   *
   * Separate from `client` because OAuth needs a configured provider while MFA
   * does not. Null renders no Connected accounts block at all.
   */
  oauthClient?: OAuthLinksClient | null;
  /** The providers that deployment has configured. See `oauthClient`. */
  availableProviders?: readonly OAuthProviderInfo[];
  /**
   * The four passkey management routes, or null where they are not offered.
   *
   * Separate from `client` for the reason `oauthClient` is. Needs no availability
   * list, since every passkey route reports the capability as `unavailable`.
   */
  passkeysClient?: PasskeysClient | null;
  className?: string;
}

/**
 * A sentence for each refusal reason the five routes can answer with.
 *
 * Fallbacks only: the server's own message is preferred. They differ per reason
 * because the remedy does.
 */
const REASON_FALLBACKS: Record<string, string> = {
  'invalid-code': 'That code is not valid. Check the app and try again.',
  'already-enabled':
    'This account already has an authenticator app. Turn the current one off before adding another.',
  'no-pending-enrolment':
    'That enrolment is no longer pending. Start again to get a new secret.',
  'rate-limited': 'Too many attempts. Wait a few minutes and try again.',
  unavailable: 'Two factor authentication is not available on this deployment.',
};

/** The sentence to render for a refusal, preferring the server's own. */
function refusalMessage(refusal: {
  reason: string;
  message: string;
  retryAfter?: number | undefined;
}): string {
  const base =
    refusal.message.trim() !== ''
      ? refusal.message
      : (REASON_FALLBACKS[refusal.reason] ?? 'That request was refused.');
  if (refusal.reason === 'rate-limited' && refusal.retryAfter !== undefined) {
    return `${base} Try again in ${refusal.retryAfter} seconds.`;
  }
  return base;
}

/** Copies text, reporting whether the platform allowed it. */
async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}

/** A button that copies a value and says so for a moment afterwards. */
const CopyButton: React.FC<{ value: string; label: string }> = ({
  value,
  label,
}) => {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');

  const handleClick = useCallback(() => {
    void copyText(value).then(ok => {
      setState(ok ? 'copied' : 'failed');
      window.setTimeout(() => setState('idle'), 2000);
    });
  }, [value]);

  return (
    <Button variant="outline" size="sm" onClick={handleClick}>
      {state === 'copied'
        ? 'Copied'
        : state === 'failed'
          ? 'Copy failed'
          : label}
    </Button>
  );
};

/** The provisioning URI as an inline SVG QR code, with the seed underneath. */
const ProvisioningQr: React.FC<{ uri: string; secret: string }> = ({
  uri,
  secret,
}) => {
  let drawing: { path: string; viewBox: string } | null = null;
  try {
    drawing = qrCodeSvgPath(uri);
  } catch {
    drawing = null;
  }

  return (
    <div className="flex flex-col items-center gap-4">
      {drawing === null ? (
        <p className="text-sm text-gray-600 dark:text-gray-400">
          This URI is too long to draw as a QR code. Enter the setup key below
          by hand.
        </p>
      ) : (
        <svg
          role="img"
          aria-label="QR code for the authenticator app"
          viewBox={drawing.viewBox}
          className="w-56 h-56 bg-white rounded"
          shapeRendering="crispEdges"
        >
          <path d={drawing.path} fill="#000000" />
        </svg>
      )}
      <div className="w-full">
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Setup key
        </p>
        <div className="flex items-center gap-2">
          <code
            data-testid="totp-secret"
            className="flex-1 px-3 py-2 bg-gray-100 dark:bg-gray-700 rounded text-sm break-all text-gray-900 dark:text-gray-100"
          >
            {secret}
          </code>
          <CopyButton value={secret} label="Copy key" />
        </div>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Scan the code, or enter the key by hand if you cannot scan. You can
          also{' '}
          <a
            href={uri}
            className="text-blue-600 dark:text-blue-400 underline break-all"
          >
            open the setup link
          </a>{' '}
          on this device. This key is shown once and cannot be read back.
        </p>
      </div>
    </div>
  );
};

/** The one time recovery code list, behind an explicit confirmation. */
const RecoveryCodes: React.FC<{
  codes: string[];
  onConfirm: () => void;
}> = ({ codes, onConfirm }) => {
  const [saved, setSaved] = useState(false);

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-base font-semibold text-gray-900 dark:text-white">
          Recovery codes
        </h4>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          Save these somewhere you can reach without your phone. Each one works
          once, in the same field as an authenticator code. They are shown here
          only this once, and generating a new set replaces every code in this
          one.
        </p>
      </div>
      <ul
        data-testid="recovery-codes"
        className="grid grid-cols-1 sm:grid-cols-2 gap-2 p-4 bg-gray-100 dark:bg-gray-700 rounded"
      >
        {codes.map(code => (
          <li
            key={code}
            className="font-mono text-sm text-gray-900 dark:text-gray-100"
          >
            {code}
          </li>
        ))}
      </ul>
      <div className="flex items-center gap-3">
        <CopyButton value={codes.join('\n')} label="Copy codes" />
      </div>
      <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input
          type="checkbox"
          checked={saved}
          onChange={e => setSaved(e.target.checked)}
          className="rounded border-gray-300 dark:border-gray-600"
        />
        I have saved these codes
      </label>
      <Button variant="primary" onClick={onConfirm} disabled={!saved}>
        Done
      </Button>
    </div>
  );
};

/** A small form that collects one code and runs an action with it. */
const CodePrompt: React.FC<{
  id: string;
  title: string;
  description: string;
  submitLabel: string;
  busy: boolean;
  onSubmit: (code: string) => void;
  onCancel: () => void;
}> = ({ id, title, description, submitLabel, busy, onSubmit, onCancel }) => {
  const [code, setCode] = useState('');

  return (
    <form
      className="space-y-3 p-4 border border-gray-200 dark:border-gray-700 rounded"
      onSubmit={e => {
        e.preventDefault();
        onSubmit(code.trim());
      }}
    >
      <h4 className="text-base font-semibold text-gray-900 dark:text-white">
        {title}
      </h4>
      <p className="text-sm text-gray-600 dark:text-gray-400">{description}</p>
      <div>
        <label
          htmlFor={id}
          className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
        >
          Authenticator or recovery code
        </label>
        <input
          id={id}
          type="text"
          value={code}
          onChange={e => setCode(e.target.value)}
          autoComplete="one-time-code"
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-700 dark:text-white"
          required
          disabled={busy}
        />
      </div>
      <div className="flex gap-3">
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? 'Working...' : submitLabel}
        </Button>
        <Button variant="outline" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
};

/** Renders the TOTP, connected account and passkey management blocks. */
export const SecuritySection: React.FC<SecuritySectionProps> = ({
  client,
  oauthClient = null,
  availableProviders = [],
  passkeysClient = null,
  className = '',
}) => {
  const [factor, setFactor] = useState<FactorState>('unknown');
  const [enrol, setEnrol] = useState<EnrolStep>({ step: 'idle' });
  const [prompt, setPrompt] = useState<'none' | 'disable' | 'regenerate'>(
    'none'
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  /** Runs one MFA call, turning a thrown error into a rendered sentence. */
  const run = useCallback(
    async <T,>(call: () => Promise<T>): Promise<T | null> => {
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        return await call();
      } catch {
        setError('That request could not be completed. Try again.');
        return null;
      } finally {
        setBusy(false);
      }
    },
    []
  );

  const handleEnrol = useCallback(async () => {
    const outcome = await run(() => client.enrolTotp());
    if (outcome === null) return;
    if (outcome.ok) {
      setEnrol({
        step: 'scanning',
        secret: outcome.secret,
        provisioningUri: outcome.provisioningUri,
      });
      return;
    }
    if (outcome.reason === 'already-enabled') {
      setFactor('enabled');
    }
    setError(refusalMessage(outcome));
  }, [client, run]);

  const handleActivate = useCallback(
    async (code: string) => {
      const outcome = await run(() => client.activateTotp({ code }));
      if (outcome === null) return;
      if (outcome.ok) {
        setFactor('enabled');
        setEnrol({ step: 'codes', codes: outcome.recoveryCodes });
        return;
      }
      setError(refusalMessage(outcome));
    },
    [client, run]
  );

  const handleDisable = useCallback(
    async (code: string) => {
      const outcome = await run(() => client.disableTotp({ code }));
      if (outcome === null) return;
      if (outcome.ok) {
        setFactor('disabled');
        setPrompt('none');
        setEnrol({ step: 'idle' });
        setNotice(
          'The authenticator app is off. Every recovery code for it is void.'
        );
        return;
      }
      setError(refusalMessage(outcome));
    },
    [client, run]
  );

  const handleRegenerate = useCallback(
    async (code: string) => {
      const outcome = await run(() => client.regenerateRecoveryCodes({ code }));
      if (outcome === null) return;
      if (outcome.ok) {
        setPrompt('none');
        setEnrol({ step: 'codes', codes: outcome.recoveryCodes });
        return;
      }
      setError(refusalMessage(outcome));
    },
    [client, run]
  );

  const statusLine =
    factor === 'enabled'
      ? 'An authenticator app is set up on this account.'
      : factor === 'disabled'
        ? 'No authenticator app is set up on this account.'
        : 'Whether an authenticator app is set up is not shown here. The identity service has no route that reports it, on purpose, so this page can only report what it has seen since the page loaded.';

  return (
    <div className={className}>
      <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
        Security
      </h2>
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
        A second factor for signing in to this panel, using a time based code
        from an authenticator app.
      </p>

      {error !== null && (
        <div
          role="alert"
          className="mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded"
        >
          {error}
        </div>
      )}
      {notice !== null && (
        <div
          role="status"
          className="mb-4 p-3 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 rounded"
        >
          {notice}
        </div>
      )}

      <p
        data-testid="factor-status"
        className="mb-6 text-sm text-gray-700 dark:text-gray-300"
      >
        {statusLine}
      </p>

      {enrol.step === 'codes' ? (
        <RecoveryCodes
          codes={enrol.codes}
          onConfirm={() => setEnrol({ step: 'idle' })}
        />
      ) : enrol.step === 'scanning' ? (
        <div className="space-y-6 max-w-md">
          <ProvisioningQr uri={enrol.provisioningUri} secret={enrol.secret} />
          <CodePrompt
            id="totp-activate-code"
            title="Confirm the app"
            description="Enter the code your authenticator app shows now. This turns the second factor on and issues your recovery codes."
            submitLabel="Turn on"
            busy={busy}
            onSubmit={code => void handleActivate(code)}
            onCancel={() => {
              setEnrol({ step: 'idle' });
              setError(null);
            }}
          />
        </div>
      ) : prompt === 'disable' ? (
        <div className="max-w-md">
          <CodePrompt
            id="totp-disable-code"
            title="Turn off the authenticator app"
            description="Enter a current code from the app, or one of your recovery codes. Turning the factor off also voids every recovery code."
            submitLabel="Turn off"
            busy={busy}
            onSubmit={code => void handleDisable(code)}
            onCancel={() => {
              setPrompt('none');
              setError(null);
            }}
          />
        </div>
      ) : prompt === 'regenerate' ? (
        <div className="max-w-md">
          <CodePrompt
            id="recovery-regenerate-code"
            title="Generate new recovery codes"
            description="Enter a current code from the app, or one of your remaining recovery codes. The new set replaces every code in the old one."
            submitLabel="Generate"
            busy={busy}
            onSubmit={code => void handleRegenerate(code)}
            onCancel={() => {
              setPrompt('none');
              setError(null);
            }}
          />
        </div>
      ) : (
        <div className="flex flex-wrap gap-3">
          <Button
            variant="primary"
            onClick={() => void handleEnrol()}
            disabled={busy}
          >
            {busy ? 'Working...' : 'Set up an authenticator app'}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setPrompt('regenerate');
              setError(null);
              setNotice(null);
            }}
            disabled={busy}
          >
            Generate new recovery codes
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setPrompt('disable');
              setError(null);
              setNotice(null);
            }}
            disabled={busy}
          >
            Turn off the authenticator app
          </Button>
        </div>
      )}

      {passkeysClient !== null && (
        <PasskeysPanel
          client={passkeysClient}
          className="mt-10 pt-8 border-t border-gray-200 dark:border-gray-700"
        />
      )}

      {oauthClient !== null && (
        <ConnectedAccounts
          client={oauthClient}
          availableProviders={availableProviders}
          className="mt-10 pt-8 border-t border-gray-200 dark:border-gray-700"
        />
      )}
    </div>
  );
};
