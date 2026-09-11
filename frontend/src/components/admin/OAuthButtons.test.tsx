import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import type { AuthClient } from '@webbpulse/auth';

import { OAuthButtons } from './OAuthButtons';
import { useOAuthProviders } from '../../hooks/useOAuthProviders';
import {
  resetAvailabilityCache,
  resetProviderCache,
} from '../../services/oauthAvailability';

// The gate is the subject: a button must never appear for a provider the
// backend cannot sign a user in with. Since webbpulse-python 0.16.0 that is
// read from `GET /api/auth/oauth/providers` in one request rather than inferred
// from a probe of each provider's start route, so what these tests drive is one
// fetch and the list it returns.

const ORIGIN = 'https://api.example.test';
const START = `${ORIGIN}/api/auth/oauth`;
const PROVIDERS_URL = `${ORIGIN}/api/auth/oauth/providers`;

/** The wire shape the discovery route answers with. */
const GOOGLE = { id: 'google', display_name: 'Google' };
const GITHUB = { id: 'github', display_name: 'GitHub' };

describe('OAuthButtons', () => {
  it('renders nothing for an empty provider list', () => {
    const { container } = render(
      <OAuthButtons providers={[]} startUrl={p => `${START}/${p}/start`} />
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('renders a real link per provider, not a button', () => {
    // The start route answers 302 to a cross-origin provider, which script
    // cannot follow, so an anchor is the element that actually works. It is
    // also middle-clickable and announced as a link.
    render(
      <OAuthButtons
        providers={[GOOGLE, GITHUB]}
        startUrl={p => `${START}/${p}/start?return_to=%2Fadmin`}
      />
    );

    const google = screen.getByTestId('oauth-start-google');
    expect(google.tagName).toBe('A');
    expect(google).toHaveAttribute(
      'href',
      `${START}/google/start?return_to=%2Fadmin`
    );
    expect(screen.getByTestId('oauth-start-github')).toBeInTheDocument();
  });

  it('labels each button with the name the backend gave', () => {
    render(
      <OAuthButtons
        providers={[GOOGLE, GITHUB]}
        startUrl={p => `${START}/${p}/start`}
      />
    );

    expect(screen.getByText(/sign in with google/i)).toBeInTheDocument();
    expect(screen.getByText(/sign in with github/i)).toBeInTheDocument();
  });

  it('renders a provider this build has never heard of', () => {
    // The point of rendering `display_name` rather than looking a name up: a
    // provider added in a future package release gets a correctly labelled
    // button with no change to this repository. It has no icon, and that is the
    // only thing it is missing.
    render(
      <OAuthButtons
        providers={[{ id: 'gitlab', display_name: 'GitLab' }]}
        startUrl={p => `${START}/${p}/start`}
      />
    );

    expect(screen.getByTestId('oauth-start-gitlab')).toHaveAttribute(
      'href',
      `${START}/gitlab/start`
    );
    expect(screen.getByText(/sign in with gitlab/i)).toBeInTheDocument();
  });
});

/** Renders the hook's result as one testid per offered provider. */
const Probe: React.FC<{ client: AuthClient<unknown> | null }> = ({
  client,
}) => {
  const providers = useOAuthProviders(client, ORIGIN);
  return (
    <ul>
      {providers.map(p => (
        <li key={p.id} data-testid={`available-${p.id}`}>
          {p.display_name}
        </li>
      ))}
    </ul>
  );
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

/** The slice of `AuthClient` the hook touches. */
function stubAuthClient(): AuthClient<unknown> {
  return {
    oauthStartUrl: (provider: string) => `${START}/${provider}/start`,
  } as unknown as AuthClient<unknown>;
}

describe('useOAuthProviders', () => {
  beforeEach(() => {
    resetAvailabilityCache();
    resetProviderCache();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    resetAvailabilityCache();
    resetProviderCache();
  });

  it('offers nothing in bearer mode, where there is no identity client', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    render(<Probe client={null} />);

    await waitFor(() => {
      expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('offers exactly the providers the backend listed, in one request', async () => {
    // One fetch for the whole list, where the old gate made one per provider
    // and spent the start route's own rate limit budget doing it.
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [GOOGLE] }));
    vi.stubGlobal('fetch', fetchMock);

    render(<Probe client={stubAuthClient()} />);

    expect(await screen.findByTestId('available-google')).toBeInTheDocument();
    expect(screen.queryByTestId('available-github')).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(PROVIDERS_URL);
  });

  it('offers nothing when the deployment has no OAuth configured', async () => {
    // The deployed state of this repository today, and a real answer: the route
    // mounts in every deployment so that "none" can be said out loud.
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [] }));
    vi.stubGlobal('fetch', fetchMock);

    render(<Probe client={stubAuthClient()} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
    expect(screen.queryByTestId('available-github')).not.toBeInTheDocument();
  });

  it('offers nothing against a backend older than 0.16.0', async () => {
    // No discovery route, so nothing to render. Reached by there being no list
    // rather than by reading a 404 as an empty one.
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, 404));
    vi.stubGlobal('fetch', fetchMock);

    render(<Probe client={stubAuthClient()} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
  });

  it('offers nothing when the request could not be made', async () => {
    // A failed request is not evidence a provider is off, but rendering a
    // button that might not work is worse than rendering none.
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('failed'));
    vi.stubGlobal('fetch', fetchMock);

    render(<Probe client={stubAuthClient()} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
  });
});
