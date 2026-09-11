import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clearAvailabilityMemoryCache,
  resetAvailabilityCache,
} from './availabilityCache';
import {
  passkeyLoginAvailability,
  probePasskeyLogin,
} from './passkeyAvailability';

// The subject is the classification, which is the whole gate: a wrong answer
// either hides a working button or shows one that 404s. Every case below is a
// real thing the login options route can answer.

const OPTIONS = 'https://api.example.test/api/auth/login/passkey/options';

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('probePasskeyLogin', () => {
  it('reads a challenge as available', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(
          { challenge_id: 'c1', publicKey: { challenge: 'abc' } },
          200
        )
      );

    await expect(probePasskeyLogin(OPTIONS, fetchImpl as never)).resolves.toBe(
      'available'
    );
  });

  it('posts anonymously with no email', async () => {
    // The probe asks about the deployment, not about an account. An address in
    // the body would be a request for a specific user's credentials, which is
    // not the question and not something the probe has in hand.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ challenge_id: 'c1' }, 200));

    await probePasskeyLogin(OPTIONS, fetchImpl as never);

    const init = fetchImpl.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('omit');
    expect(init.body).toBe('{}');
  });

  it('reads a 404 as unavailable, which is the routes not being mounted', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(null, {
        status: 404,
      })
    );

    await expect(probePasskeyLogin(OPTIONS, fetchImpl as never)).resolves.toBe(
      'unavailable'
    );
  });

  it('reads PASSKEY_LOGIN_DISABLED as unavailable', async () => {
    // Enrolment still works on this deployment and passwordless sign-in does
    // not, which is exactly the case the login button has to hide for.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ error_code: 'PASSKEY_LOGIN_DISABLED' }, 403)
      );

    await expect(probePasskeyLogin(OPTIONS, fetchImpl as never)).resolves.toBe(
      'unavailable'
    );
  });

  it('reads PASSKEYS_DISABLED as unavailable', async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ error_code: 'PASSKEYS_DISABLED' }, 503)
      );

    await expect(probePasskeyLogin(OPTIONS, fetchImpl as never)).resolves.toBe(
      'unavailable'
    );
  });

  it('reads some other 400 as unknown rather than unavailable', async () => {
    // A refusal that is not one of the two capability codes says nothing about
    // configuration, and reading it as "off" would hide a working button.
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ error_code: 'VALIDATION_ERROR' }, 400));

    await expect(probePasskeyLogin(OPTIONS, fetchImpl as never)).resolves.toBe(
      'unknown'
    );
  });

  it('reads a rate limit as unknown', async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(null, {
        status: 429,
      })
    );

    await expect(probePasskeyLogin(OPTIONS, fetchImpl as never)).resolves.toBe(
      'unknown'
    );
  });

  it('reads a network failure as unknown', async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError('failed'));

    await expect(probePasskeyLogin(OPTIONS, fetchImpl as never)).resolves.toBe(
      'unknown'
    );
  });
});

describe('passkeyLoginAvailability', () => {
  afterEach(() => {
    resetAvailabilityCache();
  });

  it('probes once per page load', async () => {
    resetAvailabilityCache();
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ challenge_id: 'c1' }, 200));

    await passkeyLoginAvailability(OPTIONS, fetchImpl as never);
    await passkeyLoginAvailability(OPTIONS, fetchImpl as never);

    // One request, not two. The route costs a challenge row and one of the
    // thirty login options calls per fifteen minutes.
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('does not cache an unknown answer', async () => {
    resetAvailabilityCache();
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 429 }))
      .mockResolvedValue(jsonResponse({ challenge_id: 'c1' }, 200));

    await expect(
      passkeyLoginAvailability(OPTIONS, fetchImpl as never)
    ).resolves.toBe('unknown');
    // A probe that learned nothing is retried rather than hiding the button
    // for the life of the page.
    await expect(
      passkeyLoginAvailability(OPTIONS, fetchImpl as never)
    ).resolves.toBe('available');
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });
});

// The point of the session tier: a reload used to cost another of the thirty
// login options calls per fifteen minutes, and another challenge row. These
// tests simulate a reload by clearing only the in-memory cache, which is what
// a page load actually does, and leaving `sessionStorage` alone.

/** Drops the memory tier the way a reload does, keeping session storage. */
function simulateReload(): void {
  clearAvailabilityMemoryCache();
}

describe('passkeyLoginAvailability across a reload', () => {
  afterEach(() => {
    resetAvailabilityCache();
  });

  it('does not probe again after a reload', async () => {
    resetAvailabilityCache();
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ challenge_id: 'c1' }, 200));

    await expect(
      passkeyLoginAvailability(OPTIONS, fetchImpl as never)
    ).resolves.toBe('available');

    simulateReload();

    await expect(
      passkeyLoginAvailability(OPTIONS, fetchImpl as never)
    ).resolves.toBe('available');
    // One request for the whole session, not one per page load.
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('remembers unavailable across a reload too', async () => {
    // Hiding the button is as much a deployment fact as showing it, and
    // re-probing to rediscover it costs exactly as much.
    resetAvailabilityCache();
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 404 }));

    await passkeyLoginAvailability(OPTIONS, fetchImpl as never);
    simulateReload();

    await expect(
      passkeyLoginAvailability(OPTIONS, fetchImpl as never)
    ).resolves.toBe('unavailable');
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it('does not persist an unknown answer', async () => {
    // A probe that failed once must not silence the affordance for the rest of
    // the session, which is the failure mode a persistent cache invites.
    resetAvailabilityCache();
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 429 }))
      .mockImplementation(() =>
        Promise.resolve(jsonResponse({ challenge_id: 'c1' }, 200))
      );

    await expect(
      passkeyLoginAvailability(OPTIONS, fetchImpl as never)
    ).resolves.toBe('unknown');

    simulateReload();

    await expect(
      passkeyLoginAvailability(OPTIONS, fetchImpl as never)
    ).resolves.toBe('available');
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('keys the stored answer by URL, so a different backend re-probes', async () => {
    resetAvailabilityCache();
    const other = 'https://other.example.test/api/auth/login/passkey/options';
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse({ challenge_id: 'c1' }, 200));

    await passkeyLoginAvailability(OPTIONS, fetchImpl as never);
    simulateReload();
    await passkeyLoginAvailability(other, fetchImpl as never);

    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it('still probes once per page load when storage throws', async () => {
    // A browser set to block site data throws on the accessor itself rather
    // than returning null. The gate has to degrade to the old behaviour, not
    // break.
    resetAvailabilityCache();
    const blocked = {
      get length(): number {
        throw new Error('blocked');
      },
      getItem(): string | null {
        throw new Error('blocked');
      },
      setItem(): void {
        throw new Error('blocked');
      },
      removeItem(): void {
        throw new Error('blocked');
      },
      key(): string | null {
        throw new Error('blocked');
      },
      clear(): void {
        throw new Error('blocked');
      },
    };
    const original = Object.getOwnPropertyDescriptor(
      globalThis,
      'sessionStorage'
    );
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true,
      get: () => blocked,
    });

    try {
      const fetchImpl = vi
        .fn()
        .mockResolvedValue(jsonResponse({ challenge_id: 'c1' }, 200));

      await expect(
        passkeyLoginAvailability(OPTIONS, fetchImpl as never)
      ).resolves.toBe('available');
      // Cached in memory for this page load, which is all that is left.
      await passkeyLoginAvailability(OPTIONS, fetchImpl as never);
      expect(fetchImpl).toHaveBeenCalledTimes(1);

      simulateReload();

      // And re-probed after a reload, because nothing could be stored.
      await expect(
        passkeyLoginAvailability(OPTIONS, fetchImpl as never)
      ).resolves.toBe('available');
      expect(fetchImpl).toHaveBeenCalledTimes(2);
    } finally {
      if (original !== undefined) {
        Object.defineProperty(globalThis, 'sessionStorage', original);
      }
    }
  });
});
