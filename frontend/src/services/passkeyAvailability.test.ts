import { afterEach, describe, expect, it, vi } from 'vitest';

import { resetAvailabilityCache } from './availabilityCache';
import {
  PASSKEY_AVAILABILITY_PATH,
  fetchPasskeyAvailability,
  passkeyAvailability,
  passkeyLoginOffered,
  resetPasskeyAvailabilityCache,
} from './passkeyAvailability';

// The subject is the reading of one route's answer, which is the whole gate: a
// wrong answer either hides a working button or shows one that fails inside
// the browser's own dialog, where there is nowhere to put an explanation.

const ORIGIN = 'https://api.example.test';
const URL = `${ORIGIN}${PASSKEY_AVAILABILITY_PATH}`;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

/** A stub that answers a fresh `Response` per call, since a body reads once. */
function answering(body: unknown, status = 200) {
  return vi
    .fn()
    .mockImplementation(() => Promise.resolve(jsonResponse(body, status)));
}

function reset(): void {
  resetAvailabilityCache();
  resetPasskeyAvailabilityCache();
}

describe('fetchPasskeyAvailability', () => {
  it('reads both booleans off the documented envelope', async () => {
    const fetchImpl = answering({ enabled: true, passwordless: true });

    await expect(
      fetchPasskeyAvailability(URL, fetchImpl as never)
    ).resolves.toEqual({ enabled: true, passwordless: true });
  });

  it('reads passkeys enabled without passwordless sign-in', async () => {
    // The distinction the old probe could only see as the difference between
    // two error codes. Here it is two fields, and a settings page and a sign-in
    // page read different ones.
    const fetchImpl = answering({ enabled: true, passwordless: false });

    await expect(
      fetchPasskeyAvailability(URL, fetchImpl as never)
    ).resolves.toEqual({ enabled: true, passwordless: false });
  });

  it('reads the switched-off deployment as a real answer', async () => {
    // Not an inference from a 404. The route mounts in every deployment, which
    // is what makes `{"enabled": false}` mean "no passkeys, and I am sure".
    const fetchImpl = answering({ enabled: false, passwordless: false });

    await expect(
      fetchPasskeyAvailability(URL, fetchImpl as never)
    ).resolves.toEqual({ enabled: false, passwordless: false });
  });

  it('gets it anonymously, with no body and no credentials', async () => {
    // A sign-in page holds no session by definition and the route reads
    // nothing off one. It is also a GET now rather than a POST that wrote a
    // WebAuthn challenge row per sign-in page load.
    const fetchImpl = answering({ enabled: true, passwordless: true });

    await fetchPasskeyAvailability(URL, fetchImpl as never);

    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('GET');
    expect(init.credentials).toBe('omit');
    expect(init.body).toBeUndefined();
  });

  it('learns nothing from a 404, which is a backend older than 0.17.0', async () => {
    // Deliberately `undefined` rather than a pair of falses. The caller turns
    // it into "render nothing", but it must not be cached as a deployment fact:
    // a 404 here is a routing mistake or an old backend, not a statement.
    const fetchImpl = vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(new Response(null, { status: 404 }))
      );

    await expect(
      fetchPasskeyAvailability(URL, fetchImpl as never)
    ).resolves.toBeUndefined();
  });

  it('learns nothing from a 500', async () => {
    const fetchImpl = vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(new Response(null, { status: 500 }))
      );

    await expect(
      fetchPasskeyAvailability(URL, fetchImpl as never)
    ).resolves.toBeUndefined();
  });

  it('learns nothing from a 200 that is not the envelope', async () => {
    // A proxy answering 200 with an HTML error page must not read as a
    // deployment with passkeys switched off.
    const fetchImpl = vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(new Response('<html>nope</html>', { status: 200 }))
      );

    await expect(
      fetchPasskeyAvailability(URL, fetchImpl as never)
    ).resolves.toBeUndefined();
  });

  it('learns nothing from a body missing passwordless', async () => {
    // Both fields are required rather than defaulted: guessing the one the
    // response did not state is the inference this route was added to remove.
    const fetchImpl = answering({ enabled: true });

    await expect(
      fetchPasskeyAvailability(URL, fetchImpl as never)
    ).resolves.toBeUndefined();
  });

  it('learns nothing from non-boolean fields', async () => {
    const fetchImpl = answering({ enabled: 'true', passwordless: 'true' });

    await expect(
      fetchPasskeyAvailability(URL, fetchImpl as never)
    ).resolves.toBeUndefined();
  });

  it('learns nothing from a network failure', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('failed'));

    await expect(
      fetchPasskeyAvailability(URL, fetchImpl as never)
    ).resolves.toBeUndefined();
  });
});

describe('passkeyAvailability', () => {
  afterEach(reset);

  it('fetches once per page load', async () => {
    reset();
    const fetchImpl = answering({ enabled: true, passwordless: true });

    await passkeyAvailability(ORIGIN, fetchImpl as never);
    await passkeyAvailability(ORIGIN, fetchImpl as never);

    // One request. The cache is here to coalesce two components asking on the
    // same paint, not to save a rate limit slot: the route is unrated and
    // carries `Cache-Control: public, max-age=300`.
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('builds the URL from the origin and the package path', async () => {
    reset();
    const fetchImpl = answering({ enabled: true, passwordless: true });

    await passkeyAvailability(ORIGIN, fetchImpl as never);

    expect(fetchImpl.mock.calls[0]?.[0]).toBe(URL);
  });

  it('keeps a switched-off answer for the life of the page', async () => {
    reset();
    const fetchImpl = answering({ enabled: false, passwordless: false });

    await expect(
      passkeyAvailability(ORIGIN, fetchImpl as never)
    ).resolves.toEqual({ enabled: false, passwordless: false });
    await passkeyAvailability(ORIGIN, fetchImpl as never);

    // A deployment fact does not change under the page, so it is not re-asked.
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('does not cache an answer it could not read', async () => {
    reset();
    const fetchImpl = vi
      .fn()
      .mockImplementationOnce(() =>
        Promise.resolve(new Response(null, { status: 500 }))
      )
      .mockImplementation(() =>
        Promise.resolve(jsonResponse({ enabled: true, passwordless: true }))
      );

    await expect(
      passkeyAvailability(ORIGIN, fetchImpl as never)
    ).resolves.toEqual({ enabled: false, passwordless: false });
    // One blip must not silence the affordance for the life of the page.
    await expect(
      passkeyAvailability(ORIGIN, fetchImpl as never)
    ).resolves.toEqual({ enabled: true, passwordless: true });
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('keys the answer by origin, so a different backend is asked', async () => {
    reset();
    const fetchImpl = answering({ enabled: true, passwordless: true });

    await passkeyAvailability(ORIGIN, fetchImpl as never);
    await passkeyAvailability('https://other.example.test', fetchImpl as never);

    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('coalesces two callers asking on the same paint', async () => {
    // The login form and its passkey button both ask on first paint. Caching
    // the in-flight promise is what makes the second join the first rather
    // than race it.
    reset();
    const fetchImpl = answering({ enabled: true, passwordless: true });

    await Promise.all([
      passkeyAvailability(ORIGIN, fetchImpl as never),
      passkeyAvailability(ORIGIN, fetchImpl as never),
    ]);

    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});

describe('passkeyLoginOffered', () => {
  afterEach(reset);

  it('is true only when the deployment says passwordless', async () => {
    reset();
    const fetchImpl = answering({ enabled: true, passwordless: true });

    await expect(passkeyLoginOffered(ORIGIN, fetchImpl as never)).resolves.toBe(
      true
    );
  });

  it('is false where passkeys are enrolment only', async () => {
    reset();
    const fetchImpl = answering({ enabled: true, passwordless: false });

    await expect(passkeyLoginOffered(ORIGIN, fetchImpl as never)).resolves.toBe(
      false
    );
  });

  it('is false where nothing could be learned', async () => {
    reset();
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('failed'));

    await expect(passkeyLoginOffered(ORIGIN, fetchImpl as never)).resolves.toBe(
      false
    );
  });
});
