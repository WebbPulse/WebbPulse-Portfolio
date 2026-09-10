import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import type { AuthClient } from '@webbpulse/auth';

import { OAuthButtons } from './OAuthButtons';
import { useOAuthProviders } from '../../hooks/useOAuthProviders';
import { resetAvailabilityCache } from '../../services/oauthAvailability';

// The gate is the subject: a button must never appear for a provider the
// backend has no route for, because pressing it is a 404 rather than a
// sign-in, and webbpulse-python 0.14.0 publishes no discovery document that
// would answer the question directly.

const START = 'https://api.example.test/api/auth/oauth';

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
        providers={['google', 'github']}
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

  it('names each provider in the label', () => {
    render(
      <OAuthButtons
        providers={['google', 'github']}
        startUrl={p => `${START}/${p}/start`}
      />
    );

    expect(screen.getByText(/sign in with google/i)).toBeInTheDocument();
    expect(screen.getByText(/sign in with github/i)).toBeInTheDocument();
  });
});

/** Renders the hook's result as one testid per available provider. */
const Probe: React.FC<{ client: AuthClient<unknown> | null }> = ({
  client,
}) => {
  const providers = useOAuthProviders(client);
  return (
    <ul>
      {providers.map(p => (
        <li key={p} data-testid={`available-${p}`}>
          {p}
        </li>
      ))}
    </ul>
  );
};

/**
 * A response with a `type` and a `status` the constructor will not accept.
 *
 * An opaque redirect really does carry status 0, and `new Response` refuses
 * anything outside 200 to 599, so both fields are defined onto a valid
 * response rather than passed in.
 */
function typedResponse(type: ResponseType, status: number): Response {
  const response = new Response(null, { status: 200 });
  Object.defineProperty(response, 'type', { value: type });
  Object.defineProperty(response, 'status', { value: status });
  return response;
}

/** The slice of `AuthClient` the hook touches. */
function stubAuthClient(): AuthClient<unknown> {
  return {
    oauthStartUrl: (provider: string) => `${START}/${provider}/start`,
  } as unknown as AuthClient<unknown>;
}

describe('useOAuthProviders', () => {
  it('offers nothing in bearer mode, where there is no identity client', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    resetAvailabilityCache();

    render(<Probe client={null} />);

    await waitFor(() => {
      expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
    });
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('offers only the providers whose start route redirects', async () => {
    resetAvailabilityCache();
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(
        url.includes('/google/')
          ? typedResponse('opaqueredirect', 0)
          : typedResponse('default', 404)
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    render(<Probe client={stubAuthClient()} />);

    expect(await screen.findByTestId('available-google')).toBeInTheDocument();
    expect(screen.queryByTestId('available-github')).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('offers nothing when the OAuth routes are not mounted at all', async () => {
    resetAvailabilityCache();
    const fetchMock = vi.fn().mockResolvedValue(typedResponse('default', 404));
    vi.stubGlobal('fetch', fetchMock);

    render(<Probe client={stubAuthClient()} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
    expect(screen.queryByTestId('available-github')).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('offers nothing when the probe could not be made', async () => {
    // A failed probe is not evidence the provider is off, but rendering a
    // button that might 404 is worse than rendering none.
    resetAvailabilityCache();
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('failed'));
    vi.stubGlobal('fetch', fetchMock);

    render(<Probe client={stubAuthClient()} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
    expect(screen.queryByTestId('available-google')).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
