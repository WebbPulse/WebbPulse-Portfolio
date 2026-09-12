import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@webbpulse/auth/react';

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
  /** Clears {@link AdminSession.sessionEndedMessage}. */
  clearSessionEnded: () => void;
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
 * `useAuth` owns the status, so the bootstrap refresh, the StrictMode double
 * mount and every post-sign-in transition land here with no local mirror to
 * disagree with them. Only the session-ended sentence is local, because the
 * package notifies through the client's `onSessionEnded` constructor option and
 * exposes no React surface for it.
 */
export function useAdminSession(): AdminSession {
  const { isAuthenticated, isLoading, logout } = useAuth();
  const [sessionEndedMessage, setSessionEndedMessage] = useState<string | null>(
    null
  );

  useEffect(
    () =>
      apiService.onSessionEnded(() => {
        setSessionEndedMessage(SESSION_ENDED_MESSAGE);
      }),
    []
  );

  const clearSessionEnded = useCallback(() => {
    setSessionEndedMessage(null);
  }, []);

  const signOut = useCallback(() => {
    void logout();
  }, [logout]);

  return {
    isAuthenticated,
    isLoading,
    sessionEndedMessage,
    clearSessionEnded,
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
    clearSessionEnded: () => {},
    markAuthenticated,
    logout,
  };
}
