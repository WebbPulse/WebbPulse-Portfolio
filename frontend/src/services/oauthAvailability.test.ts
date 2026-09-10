import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  probeProvider,
  providerAvailability,
  providerLabel,
  resetAvailabilityCache,
} from './oauthAvailability';

// The subject here is the classification, which is the whole gate: a wrong
// answer either hides a working provider or shows a button that 404s. There is
// no discovery endpoint on webbpulse-python 0.14.0, so every one of these
// cases is a real thing the start route can answer and the probe has to read.

const START = 'https://api.example.test/api/auth/oauth/google/start';

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

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('probeProvider', () => {
  it('reads an opaque redirect as available', async () => {
    // What `redirect: "manual"` actually produces in a browser for the 302 to
    // Google: status 0, no readable headers, and `type: "opaqueredirect"`.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(typedResponse('opaqueredirect', 0));

    await expect(probeProvider(START, fetchImpl as never)).resolves.toBe(
      'available'
    );
  });

  it('reads a visible 3xx as available', async () => {
    // Not what a browser gives, but what a test transport and some fetch
    // polyfills give, and it means the same thing.
    const fetchImpl = vi.fn().mockResolvedValue(typedResponse('default', 302));

    await expect(probeProvider(START, fetchImpl as never)).resolves.toBe(
      'available'
    );
  });

  it('reads a 404 as unavailable', async () => {
    // The routes are not mounted at all, which is the case for a deployment
    // with no client id configured for either provider.
    const fetchImpl = vi.fn().mockResolvedValue(typedResponse('default', 404));

    await expect(probeProvider(START, fetchImpl as never)).resolves.toBe(
      'unavailable'
    );
  });

  it.each(['OAUTH_PROVIDER_UNKNOWN', 'OAUTH_PROVIDER_UNAVAILABLE'])(
    'reads %s as unavailable',
    async code => {
      // The routes exist, this provider does not. The envelope carries which.
      const fetchImpl = vi
        .fn()
        .mockResolvedValue(jsonResponse({ error_code: code }, 400));

      await expect(probeProvider(START, fetchImpl as never)).resolves.toBe(
        'unavailable'
      );
    }
  );

  it('reads some other 400 as unknown rather than unavailable', async () => {
    // A refusal that is not about configuration must not hide the button: the
    // provider may be perfectly available and the request merely malformed.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ error_code: 'SOMETHING_ELSE' }, 400));

    await expect(probeProvider(START, fetchImpl as never)).resolves.toBe(
      'unknown'
    );
  });

  it('reads a rate limit as unknown', async () => {
    // A 429 says nothing about whether the provider is configured.
    const fetchImpl = vi.fn().mockResolvedValue(typedResponse('default', 429));

    await expect(probeProvider(START, fetchImpl as never)).resolves.toBe(
      'unknown'
    );
  });

  it('reads a network failure as unknown', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('failed'));

    await expect(probeProvider(START, fetchImpl as never)).resolves.toBe(
      'unknown'
    );
  });

  it('does not follow the redirect and sends no credentials', async () => {
    // Both matter. Following would chase a cross-origin 302 to Google and fail
    // on CORS there, which is indistinguishable from the network being down;
    // sending credentials would put the refresh cookie on a route that does
    // not read it.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(typedResponse('opaqueredirect', 0));

    await probeProvider(START, fetchImpl as never);

    const init = (fetchImpl.mock.calls[0] as [string, RequestInit])[1];
    expect(init.redirect).toBe('manual');
    expect(init.credentials).toBe('omit');
  });
});

describe('providerAvailability', () => {
  beforeEach(() => {
    resetAvailabilityCache();
  });

  afterEach(() => {
    resetAvailabilityCache();
  });

  it('probes once per URL and caches the answer', async () => {
    // The start route allows twenty per fifteen minutes per IP, so a login
    // page that re-probed on every render would exhaust the bucket before a
    // user finished typing a password.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(typedResponse('opaqueredirect', 0));

    await providerAvailability(START, fetchImpl as never);
    await providerAvailability(START, fetchImpl as never);

    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('shares one in-flight probe between concurrent callers', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(typedResponse('opaqueredirect', 0));

    await Promise.all([
      providerAvailability(START, fetchImpl as never),
      providerAvailability(START, fetchImpl as never),
    ]);

    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('does not cache an unknown, so a flaky probe is retried', async () => {
    const fetchImpl = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('failed'))
      .mockResolvedValueOnce(typedResponse('opaqueredirect', 0));

    await expect(providerAvailability(START, fetchImpl as never)).resolves.toBe(
      'unknown'
    );
    await expect(providerAvailability(START, fetchImpl as never)).resolves.toBe(
      'available'
    );
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('caches per URL, so two backends do not share an answer', async () => {
    const other = 'https://api.other.test/api/auth/oauth/google/start';
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(typedResponse('opaqueredirect', 0));

    await providerAvailability(START, fetchImpl as never);
    await providerAvailability(other, fetchImpl as never);

    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
});

describe('providerLabel', () => {
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
