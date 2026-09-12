import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AdminPanel } from './AdminPanel';
import { apiService } from '../../services/api';
import {
  jsonResponse,
  renderWithAuth,
  stubAuthClient,
  unauthorizedResponse,
} from '../../test-helpers/renderWithAuth';
import { useAdminSession } from '../../hooks/useAdminSession';

/** The URL of a `fetch` call, whichever of the three input forms it used. */
function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

/** Renders the panel with `getAuthClient` answering `client`. */
function renderPanel(client: ReturnType<typeof stubAuthClient> | null) {
  vi.spyOn(apiService, 'getAuthClient').mockReturnValue(client);
  vi.spyOn(apiService, 'getIdentityClient').mockReturnValue(client);
  return render(
    <MemoryRouter>
      <AdminPanel />
    </MemoryRouter>
  );
}

/** The list loads the panel fires once it is signed in. */
const CONTENT_LOADS = [
  'getProjects',
  'getExperience',
  'getAdminBlogPosts',
  'getCategories',
  'getSkills',
  'getEducation',
  'getCertifications',
] as const;

describe('AdminPanel session, lifted onto AuthProvider', () => {
  beforeEach(() => {
    for (const method of CONTENT_LOADS) {
      vi.spyOn(apiService, method).mockResolvedValue({ data: [] });
    }
    vi.spyOn(apiService, 'getSiteContent').mockResolvedValue({ data: null });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders the sign-in screen when the refresh cookie buys nothing', async () => {
    renderPanel(stubAuthClient());

    await waitFor(() => {
      expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    });
    expect(
      screen.queryByRole('heading', { name: /admin panel/i })
    ).not.toBeInTheDocument();
  });

  it('renders the panel when the provider bootstrap spends the cookie', async () => {
    const client = stubAuthClient({
      fetch: () =>
        Promise.resolve(jsonResponse({ access_token: 'a1', expires_in: 600 })),
      user: { id: 1, username: 'admin' },
    });

    renderPanel(client);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /admin panel/i })
      ).toBeInTheDocument();
    });
  });

  it('spends the refresh cookie once under a double mount', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(jsonResponse({ access_token: 'a1', expires_in: 600 }))
      );
    const client = stubAuthClient({ fetch: fetchMock, user: { id: 1 } });

    renderPanel(client);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /admin panel/i })
      ).toBeInTheDocument();
    });
    const refreshCalls = fetchMock.mock.calls.filter(([input]) =>
      String(input).endsWith('/api/auth/refresh')
    );
    expect(refreshCalls).toHaveLength(1);
  });

  it('returns to the sign-in screen when a live session ends', async () => {
    const listeners = new Set<() => void>();
    vi.spyOn(apiService, 'onSessionEnded').mockImplementation(listener => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    });

    let authorized = true;
    const client = stubAuthClient({
      fetch: (input: RequestInfo | URL) => {
        const url = requestUrl(input);
        if (url.endsWith('/api/auth/refresh')) {
          return Promise.resolve(
            authorized
              ? jsonResponse({ access_token: 'a1', expires_in: 600 })
              : unauthorizedResponse()
          );
        }
        return Promise.resolve(jsonResponse({}));
      },
      user: { id: 1, username: 'admin' },
      onSessionEnded: () => {
        for (const listener of [...listeners]) listener();
      },
    });

    renderPanel(client);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /admin panel/i })
      ).toBeInTheDocument();
    });

    authorized = false;
    await client.refresh();

    await waitFor(() => {
      expect(screen.getByText(/your session expired/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
  });

  it('renders the bearer panel with no provider when there is no client', async () => {
    vi.spyOn(apiService, 'isAuthenticated').mockReturnValue(true);

    renderPanel(null);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /admin panel/i })
      ).toBeInTheDocument();
    });
  });
});

describe('useAdminSession, the session-ended fan-out', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reports the expiry sentence to every subscriber', async () => {
    const subscribed = new Set<() => void>();
    vi.spyOn(apiService, 'onSessionEnded').mockImplementation(listener => {
      subscribed.add(listener);
      return () => subscribed.delete(listener);
    });

    function Probe() {
      const { sessionEndedMessage } = useAdminSession();
      return <span data-testid="ended">{sessionEndedMessage ?? 'none'}</span>;
    }

    renderWithAuth(<Probe />, stubAuthClient());

    await waitFor(() => {
      expect(subscribed.size).toBeGreaterThan(0);
    });
    expect(screen.getByTestId('ended').textContent).toBe('none');

    for (const listener of [...subscribed]) listener();

    await waitFor(() => {
      expect(screen.getByTestId('ended').textContent).toMatch(
        /your session expired/i
      );
    });
  });
});
