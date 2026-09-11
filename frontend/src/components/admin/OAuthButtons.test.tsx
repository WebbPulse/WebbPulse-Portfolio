import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import type { AuthClient } from '@webbpulse/auth';

import { OAuthButtons } from './OAuthButtons';
import { useOAuthProviders } from '../../hooks/useOAuthProviders';
import {
  resetAvailabilityCache,
  resetProviderCache,
} from '../../services/oauthAvailability';

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
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, 404));
    vi.stubGlobal('fetch', fetchMock);

    render(<Probe client={stubAuthClient()} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
  });

  it('offers nothing when the request could not be made', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('failed'));
    vi.stubGlobal('fetch', fetchMock);

    render(<Probe client={stubAuthClient()} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
  });
});
