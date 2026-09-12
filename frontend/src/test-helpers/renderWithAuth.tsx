import { render, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { createAuthClient, type AuthClient } from '@webbpulse/auth';
import { AuthProvider, type AnyAuthClient } from '@webbpulse/auth/react';

/** Options for {@link stubAuthClient}. */
export interface StubAuthClientOptions {
  /** Answers the refresh and session calls. Defaults to a 401, so anonymous. */
  fetch?: typeof globalThis.fetch;
  /** The user the client reports once a token is held. */
  user?: unknown;
  /** Told when the client decides a live session ended. */
  onSessionEnded?: () => void;
}

/** A JSON `Response`, which is what every identity route answers with. */
export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

/** The 401 envelope the backend answers with when there is no session. */
export function unauthorizedResponse(): Response {
  return jsonResponse(
    {
      success: false,
      status: 401,
      message: 'No session.',
      request_id: 'r-test',
    },
    401
  );
}

/**
 * A real `AuthClient` over a stubbed `fetch`.
 *
 * The real client rather than a fake, so a test exercises the same state machine
 * the panel runs against in a browser. Proactive refresh is off, since a timer
 * firing mid-test is noise rather than coverage.
 */
export function stubAuthClient(
  options: StubAuthClientOptions = {}
): AuthClient<unknown> {
  const {
    fetch = () => Promise.resolve(unauthorizedResponse()),
    user = null,
    onSessionEnded,
  } = options;

  return createAuthClient({
    baseUrl: 'https://api.example.test',
    disableProactiveRefresh: true,
    loadUser: () => Promise.resolve(user),
    clientOptions: { fetch, retries: 0 },
    ...(onSessionEnded === undefined ? {} : { onSessionEnded }),
  });
}

/**
 * Renders `children` inside `AuthProvider` and a router.
 *
 * The panel and its sign-in screens both need the two, so every admin test that
 * mounts them goes through here rather than repeating the wrapper.
 */
export function renderWithAuth(
  children: ReactNode,
  client: AuthClient<unknown>
): RenderResult {
  return render(
    <MemoryRouter>
      <AuthProvider client={client as unknown as AnyAuthClient}>
        {children}
      </AuthProvider>
    </MemoryRouter>
  );
}
