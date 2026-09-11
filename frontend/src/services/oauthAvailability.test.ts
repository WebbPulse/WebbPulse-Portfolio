import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  OAUTH_PROVIDERS_PATH,
  fetchOAuthProviders,
  oauthProviders,
  providerLabel,
  resetAvailabilityCache,
  resetProviderCache,
} from './oauthAvailability';

// The subject is the reading of one explicit list, which webbpulse-python
// 0.16.0 added and which replaced a probe of the start route per provider per
// page load. Two things have to hold. An answer the backend gave has to be
// rendered exactly as given, including the order and the display names, because
// a deployment naming its own providers is the whole point of the route. And
// anything that is not a readable answer has to come back as "nothing to draw"
// without ever being mistaken for "the backend says there are none", because
// the second is cached for the life of the page and the first must not be.

const ORIGIN = 'https://api.example.test';
const URL = `${ORIGIN}${OAUTH_PROVIDERS_PATH}`;

const GOOGLE = { id: 'google', display_name: 'Google' };
const GITHUB = { id: 'github', display_name: 'GitHub' };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('OAUTH_PROVIDERS_PATH', () => {
  it('is the route the identity package mounts', () => {
    // Spelled out rather than derived, so a path that moved in the package is a
    // failure here rather than a 404 at the gateway. The backend suite has the
    // matching assertion against the package's own constant.
    expect(OAUTH_PROVIDERS_PATH).toBe('/api/auth/oauth/providers');
  });
});

describe('fetchOAuthProviders', () => {
  it('returns the providers the backend listed, in that order', async () => {
    // The order is the deployment's own statement of which sign-in method it
    // would rather a user reached for, so it is preserved rather than sorted.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [GITHUB, GOOGLE] }));

    await expect(fetchOAuthProviders(URL, fetchImpl as never)).resolves.toEqual(
      [GITHUB, GOOGLE]
    );
  });

  it('returns an empty list for a deployment with no OAuth configured', async () => {
    // The ordinary state of this repository today, and a real answer rather
    // than an inference: the route mounts in every deployment precisely so that
    // "none" can be said out loud.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [] }));

    await expect(fetchOAuthProviders(URL, fetchImpl as never)).resolves.toEqual(
      []
    );
  });

  it('returns undefined for a 404, which means a backend older than 0.16.0', async () => {
    // Distinct from `[]` on purpose. An empty list is a fact about the
    // deployment and is kept; a missing route teaches nothing about
    // configuration and must not be cached as though it had.
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({}, 404));

    await expect(
      fetchOAuthProviders(URL, fetchImpl as never)
    ).resolves.toBeUndefined();
  });

  it('returns undefined for a 500', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({}, 500));

    await expect(
      fetchOAuthProviders(URL, fetchImpl as never)
    ).resolves.toBeUndefined();
  });

  it('returns undefined for a network failure', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('failed'));

    await expect(
      fetchOAuthProviders(URL, fetchImpl as never)
    ).resolves.toBeUndefined();
  });

  it('returns undefined for a body that is not JSON', async () => {
    // A proxy or a captive portal answering 200 with an HTML error page. It
    // must not read as a deployment with OAuth switched off.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(new Response('<html>nope</html>', { status: 200 }));

    await expect(
      fetchOAuthProviders(URL, fetchImpl as never)
    ).resolves.toBeUndefined();
  });

  it('returns undefined for JSON that is not the documented envelope', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({ items: [] }));

    await expect(
      fetchOAuthProviders(URL, fetchImpl as never)
    ).resolves.toBeUndefined();
  });

  it('drops a malformed entry rather than the whole list', async () => {
    // One bad record must not hide a provider that is described correctly,
    // because the consequence is a sign-in method silently missing.
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse({
        providers: [GOOGLE, { id: 'github' }, { display_name: 'X' }, null, 7],
      })
    );

    await expect(fetchOAuthProviders(URL, fetchImpl as never)).resolves.toEqual(
      [GOOGLE]
    );
  });

  it('sends no credentials', async () => {
    // The sign-in page has no session by definition, and sending the refresh
    // cookie to a route that does not read it is a habit worth not forming.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [] }));

    await fetchOAuthProviders(URL, fetchImpl as never);

    const init = (fetchImpl.mock.calls[0] as [string, RequestInit])[1];
    expect(init.credentials).toBe('omit');
    expect(init.method).toBe('GET');
  });
});

describe('oauthProviders', () => {
  beforeEach(() => {
    resetAvailabilityCache();
    resetProviderCache();
  });

  afterEach(() => {
    resetAvailabilityCache();
    resetProviderCache();
  });

  it('builds the URL from the identity origin', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [] }));

    await oauthProviders(ORIGIN, fetchImpl as never);

    expect(fetchImpl.mock.calls[0]?.[0]).toBe(URL);
  });

  it('fetches once per page load and caches the list', async () => {
    // One request for the whole list, where the old gate made one per provider
    // and spent the start route's own rate limit budget doing it.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [GOOGLE, GITHUB] }));

    await expect(oauthProviders(ORIGIN, fetchImpl as never)).resolves.toEqual([
      GOOGLE,
      GITHUB,
    ]);
    await expect(oauthProviders(ORIGIN, fetchImpl as never)).resolves.toEqual([
      GOOGLE,
      GITHUB,
    ]);

    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('shares one in-flight request between concurrent callers', async () => {
    // Two components mounting in the same tick is the ordinary case, not the
    // edge one: the sign-in form and the connected accounts panel both ask.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [GOOGLE] }));

    const [first, second] = await Promise.all([
      oauthProviders(ORIGIN, fetchImpl as never),
      oauthProviders(ORIGIN, fetchImpl as never),
    ]);

    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(first).toEqual([GOOGLE]);
    expect(second).toEqual([GOOGLE]);
  });

  it('caches an empty list, because "none" is a deployment fact', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [] }));

    await oauthProviders(ORIGIN, fetchImpl as never);
    await oauthProviders(ORIGIN, fetchImpl as never);

    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('does not cache a failure, so a flaky answer is retried', async () => {
    // The distinction this whole file turns on. A dropped request must not hide
    // a working sign-in method for the life of the page.
    const fetchImpl = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('failed'))
      .mockResolvedValueOnce(jsonResponse({ providers: [GOOGLE] }));

    await expect(oauthProviders(ORIGIN, fetchImpl as never)).resolves.toEqual(
      []
    );
    await expect(oauthProviders(ORIGIN, fetchImpl as never)).resolves.toEqual([
      GOOGLE,
    ]);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('renders nothing for a backend that has no discovery route', async () => {
    // A bundle newer than its backend. Hiding the buttons is right, and it is
    // reached by there being nothing to render rather than by reading a 404 as
    // an empty list.
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse({}, 404));

    await expect(oauthProviders(ORIGIN, fetchImpl as never)).resolves.toEqual(
      []
    );
  });

  it('caches per origin, so two backends do not share an answer', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ providers: [GOOGLE] }))
      .mockResolvedValueOnce(jsonResponse({ providers: [GITHUB] }));

    await expect(oauthProviders(ORIGIN, fetchImpl as never)).resolves.toEqual([
      GOOGLE,
    ]);
    await expect(
      oauthProviders('https://api.other.test', fetchImpl as never)
    ).resolves.toEqual([GITHUB]);

    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
});

describe('providerLabel', () => {
  // Still here for the linked accounts list, which comes from
  // `GET /api/auth/oauth/links` and carries provider ids and no display names.
  // A sign-in button never reaches it: the discovery route names its own
  // providers and those names are rendered as given.

  it('names the two baseline providers', () => {
    expect(providerLabel('google')).toBe('Google');
    expect(providerLabel('github')).toBe('GitHub');
  });

  it('title cases a provider this build does not know', () => {
    // The server can configure a third provider and the package explicitly
    // allows it, so a raw lowercase wire value must not reach the screen.
    expect(providerLabel('gitlab')).toBe('Gitlab');
  });
});
