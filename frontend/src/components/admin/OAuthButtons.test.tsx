import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import type { AuthClient } from '@webbpulse/auth';
import { resetAvailabilityCache } from '@webbpulse/discovery';

import { OAuthButtons } from './OAuthButtons';
import { useOAuthProviders } from '../../hooks/useOAuthProviders';

const ORIGIN = 'https://api.example.test';
const START = `${ORIGIN}/api/auth/oauth`;
const PROVIDERS_URL = `${ORIGIN}/api/auth/oauth/providers`;

/** The wire shape the discovery route answers with. */
const GOOGLE_WIRE = { id: 'google', display_name: 'Google' };

/** The normalised shape the package hands a component. */
const GOOGLE = { id: 'google', displayName: 'Google' };
const GITHUB = { id: 'github', displayName: 'GitHub' };

describe('OAuthButtons', () => {
  it('renders nothing for an empty provider list', () => {
    const { container } = render(
      <OAuthButtons providers={[]} startUrl={(p) => `${START}/${p}/start`} />
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('renders a real link per provider, not a button', () => {
    render(
      <OAuthButtons
        providers={[GOOGLE, GITHUB]}
        startUrl={(p) => `${START}/${p}/start?return_to=%2Fadmin`}
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
        startUrl={(p) => `${START}/${p}/start`}
      />
    );

    expect(screen.getByText(/sign in with google/i)).toBeInTheDocument();
    expect(screen.getByText(/sign in with github/i)).toBeInTheDocument();
  });

  it('renders a provider this build has never heard of', () => {
    render(
      <OAuthButtons
        providers={[{ id: 'gitlab', displayName: 'GitLab' }]}
        startUrl={(p) => `${START}/${p}/start`}
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
const Probe: React.FC<{
  client: AuthClient<unknown> | null;
  fetchImpl: typeof fetch;
}> = ({ client, fetchImpl }) => {
  const providers = useOAuthProviders(client, ORIGIN, fetchImpl);
  return (
    <ul>
      {providers.map((p) => (
        <li key={p.id} data-testid={`available-${p.id}`}>
          {p.displayName}
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
  });

  it('offers nothing in bearer mode, where there is no identity client', async () => {
    const fetchMock = vi.fn();

    render(<Probe client={null} fetchImpl={fetchMock as never} />);

    await waitFor(() => {
      expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('offers exactly the providers the backend listed, in one request', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [GOOGLE_WIRE] }));

    render(<Probe client={stubAuthClient()} fetchImpl={fetchMock as never} />);

    expect(await screen.findByTestId('available-google')).toBeInTheDocument();
    expect(screen.queryByTestId('available-github')).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(PROVIDERS_URL);
  });

  it('offers nothing when the deployment has no OAuth configured', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [] }));

    render(<Probe client={stubAuthClient()} fetchImpl={fetchMock as never} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
    expect(screen.queryByTestId('available-github')).not.toBeInTheDocument();
  });

  it('offers nothing against a backend older than 0.16.0', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}, 404));

    render(<Probe client={stubAuthClient()} fetchImpl={fetchMock as never} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
  });

  it('offers nothing when the request could not be made', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('failed'));

    render(<Probe client={stubAuthClient()} fetchImpl={fetchMock as never} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
  });
});
