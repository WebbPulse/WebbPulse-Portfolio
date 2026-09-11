import { afterEach, describe, expect, it, vi } from 'vitest';

import { resetAvailabilityCache } from './availabilityCache';
import {
  PASSKEY_AVAILABILITY_PATH,
  fetchPasskeyAvailability,
  passkeyAvailability,
  passkeyLoginOffered,
  resetPasskeyAvailabilityCache,
} from './passkeyAvailability';

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
    const fetchImpl = answering({ enabled: true, passwordless: false });

    await expect(
      fetchPasskeyAvailability(URL, fetchImpl as never)
    ).resolves.toEqual({ enabled: true, passwordless: false });
  });

  it('reads the switched-off deployment as a real answer', async () => {
    const fetchImpl = answering({ enabled: false, passwordless: false });

    await expect(
      fetchPasskeyAvailability(URL, fetchImpl as never)
    ).resolves.toEqual({ enabled: false, passwordless: false });
  });

  it('gets it anonymously, with no body and no credentials', async () => {
    const fetchImpl = answering({ enabled: true, passwordless: true });

    await fetchPasskeyAvailability(URL, fetchImpl as never);

    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('GET');
    expect(init.credentials).toBe('omit');
    expect(init.body).toBeUndefined();
  });

  it('learns nothing from a 404, which is a backend older than 0.17.0', async () => {
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
