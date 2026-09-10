import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { VERIFY_EMAIL_PATH, readLinkToken } from '@webbpulse/auth';
import { Button } from '../components/common';
import { apiService } from '../services/api';

/**
 * The page a verification link from the backend lands on.
 *
 * The mailed URL is `<frontend base>/verify-email?token=...`, and
 * `VERIFY_EMAIL_PATH` from `@webbpulse/auth` is the same literal both sides
 * agree on, so it is imported rather than written out again here.
 *
 * Confirming is a POST rather than a GET on purpose: a mail scanner following
 * the link to check it for malware would spend a single use token before the
 * user ever clicked. That is the backend's rule, and this page honours it by
 * calling `confirmEmailVerification` on mount rather than by being a link
 * target that verifies on load of the API route itself.
 */

/** What the page is currently showing. */
type VerifyState =
  | { kind: 'working' }
  | { kind: 'done' }
  | { kind: 'error'; title: string; detail: string }
  // Bearer mode has no identity routes to call, so the page says so rather
  // than rendering a spinner that never resolves.
  | { kind: 'unavailable' };

/**
 * The sentence for each refusal the confirm route can answer with.
 *
 * One case for invalid, expired, already used and wrong purpose, because that
 * is how the server answers: the difference between them is information about
 * somebody else's token, so it is not disclosed and this page does not invent
 * it.
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

    // `expectedPath` so a reset token pasted onto this page is not presented
    // to the verification endpoint, which the server refuses as a wrong
    // purpose token.
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
