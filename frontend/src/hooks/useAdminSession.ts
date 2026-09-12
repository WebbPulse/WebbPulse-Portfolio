import { useCallback, useState } from 'react';
import { useAuth, useSessionEnded } from '@webbpulse/auth/react';

import { apiService } from '../services/api';

/** The sentence shown when a live session ended without the user asking. */
export const SESSION_ENDED_MESSAGE =
  'Your session expired. Please sign in again.';

/** What {@link useAdminSession} reports to the admin panel. */
export interface AdminSession {
  /** True once an access token is held. */
  isAuthenticated: boolean;
  /** True until the bootstrap refresh settles. */
  isLoading: boolean;
  /** Set when a live session ended on its own, cleared on the next sign-in. */
  sessionEndedMessage: string | null;
  /**
   * Records a sign-in the client itself did not observe.
   *
   * A no-op under identity, where the client is the source of truth.
   */
  markAuthenticated: () => void;
  /** Starts a sign-out and drops the session locally. */
  logout: () => void;
}

/**
 * The identity session, read off `AuthProvider` rather than kept locally.
 *
 * `useAuth` owns the status and `useSessionEnded` owns the ending, so the
 * bootstrap refresh, the StrictMode double mount and every post-sign-in
 * transition land here with no local mirror to disagree with them. A deliberate
 * sign-out also ends the session, so only the involuntary reasons become a
 * sentence; the panel must not accuse someone of expiring when they clicked
 * Sign out.
 */
export function useAdminSession(): AdminSession {
  const { isAuthenticated, isLoading, logout } = useAuth();
  const sessionEnded = useSessionEnded();

  const signOut = useCallback(() => {
    void logout();
  }, [logout]);

  return {
    isAuthenticated,
    isLoading,
    sessionEndedMessage:
      sessionEnded !== null && sessionEnded.reason !== 'logged-out'
        ? SESSION_ENDED_MESSAGE
        : null,
    markAuthenticated: () => {},
    logout: signOut,
  };
}

/**
 * The bearer-mode stand-in, for a bundle built with no identity client.
 *
 * `AuthProvider` needs a client and bearer mode has none, so this reports the
 * stored token instead. The shape matches {@link useAdminSession} so the panel
 * reads one interface either way, and the whole branch goes away with the bearer
 * store at the identity cutover.
 */
export function useBearerSession(): AdminSession {
  const [isAuthenticated, setIsAuthenticated] = useState(() =>
    apiService.isAuthenticated()
  );

  const markAuthenticated = useCallback(() => {
    setIsAuthenticated(true);
  }, []);

  const logout = useCallback(() => {
    apiService.logout();
    setIsAuthenticated(false);
  }, []);

  return {
    isAuthenticated,
    isLoading: false,
    sessionEndedMessage: null,
    markAuthenticated,
    logout,
  };
}
