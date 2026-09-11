import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  OAUTH_PROVIDERS_PATH,
  fetchOAuthProviders,
  oauthProviders,
  providerLabel,
  resetAvailabilityCache,
  resetProviderCache,
} from './oauthAvailability';

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
    expect(OAUTH_PROVIDERS_PATH).toBe('/api/auth/oauth/providers');
  });
});

describe('fetchOAuthProviders', () => {
  it('returns the providers the backend listed, in that order', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [GITHUB, GOOGLE] }));

    await expect(fetchOAuthProviders(URL, fetchImpl as never)).resolves.toEqual(
      [GITHUB, GOOGLE]
    );
  });

  it('returns an empty list for a deployment with no OAuth configured', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ providers: [] }));

    await expect(fetchOAuthProviders(URL, fetchImpl as never)).resolves.toEqual(
      []
    );
  });

  it('returns undefined for a 404, which means a backend older than 0.16.0', async () => {
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
  it('names the two baseline providers', () => {
    expect(providerLabel('google')).toBe('Google');
    expect(providerLabel('github')).toBe('GitHub');
  });

  it('title cases a provider this build does not know', () => {
    expect(providerLabel('gitlab')).toBe('Gitlab');
  });
});
