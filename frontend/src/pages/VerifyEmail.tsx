import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { VERIFY_EMAIL_PATH, readLinkToken } from '@webbpulse/auth';
import { Button } from '../components/common';
import { apiService } from '../services/api';

/**
 * The page a verification link from the backend lands on.
 *
 * Confirms with a POST on mount, so a mail scanner following the link cannot
 * spend the single use token.
 */

/** What the page is currently showing. */
type VerifyState =
  | { kind: 'working' }
  | { kind: 'done' }
  | { kind: 'error'; title: string; detail: string }
  | { kind: 'unavailable' };

/**
 * The sentence for each refusal the confirm route can answer with.
 *
 * One case for invalid, expired, already used and wrong purpose, which is as
 * much as the server discloses.
 */
function describeRefusal(reason: string): { title: string; detail: string } {
  switch (reason) {
    case 'invalid-link':
      return {
        title: 'This link is no longer valid',
        detail:
          'It may have expired or already been used. Request a new verification email and try again.',
      };
    case 'rate-limited':
      return {
        title: 'Too many attempts',
        detail: 'Please wait a while before trying this link again.',
      };
    case 'unavailable':
      return {
        title: 'Email is not available right now',
        detail:
          'Verification is temporarily unavailable. Please try again later.',
      };
    default:
      return {
        title: 'Something went wrong',
        detail: 'We could not verify this address. Please try again later.',
      };
  }
}

/** Confirms the token on mount and reports the outcome. */
export const VerifyEmail: React.FC = () => {
  const [state, setState] = useState<VerifyState>({ kind: 'working' });

  /**
   * Guards against a second confirm in React 18 strict mode, whose double
   * invoked effects would present a single use token twice and turn a valid
   * link into an "already used" refusal on the second call.
   */
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const identity = apiService.getIdentityClient();
    if (identity === null) {
      setState({ kind: 'unavailable' });
      return;
    }

    const token = readLinkToken({ expectedPath: VERIFY_EMAIL_PATH });
    if (token === null) {
      setState({
        kind: 'error',
        title: 'This link is missing its token',
        detail:
          'Open the link from your email again, or request a new verification email.',
      });
      return;
    }

    void (async () => {
      try {
        const outcome = await identity.confirmEmailVerification({ token });
        if (outcome.ok) {
          setState({ kind: 'done' });
          return;
        }
        setState({ kind: 'error', ...describeRefusal(outcome.reason) });
      } catch {
        setState({
          kind: 'error',
          title: 'Something went wrong',
          detail: 'We could not verify this address. Please try again later.',
        });
      }
    })();
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-12">
      <div className="max-w-md mx-auto">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-8 text-center">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
            Email Verification
          </h1>

          {state.kind === 'working' && (
            <p role="status" className="text-gray-600 dark:text-gray-400">
              Verifying your email address...
            </p>
          )}

          {state.kind === 'done' && (
            <>
              <p
                role="status"
                className="text-green-700 dark:text-green-400 mb-6"
              >
                Your email address is verified. You can sign in now.
              </p>
              <Link to="/admin">
                <Button variant="primary">Go to sign in</Button>
              </Link>
            </>
          )}

          {state.kind === 'error' && (
            <div role="alert">
              <p className="font-medium text-gray-900 dark:text-white mb-2">
                {state.title}
              </p>
              <p className="text-gray-600 dark:text-gray-400 mb-6">
                {state.detail}
              </p>
              <Link to="/admin">
                <Button variant="outline">Back to sign in</Button>
              </Link>
            </div>
          )}

          {state.kind === 'unavailable' && (
            <div role="alert">
              <p className="text-gray-600 dark:text-gray-400 mb-6">
                Email verification is not enabled for this site.
              </p>
              <Link to="/">
                <Button variant="outline">Back to home</Button>
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VerifyEmail;
