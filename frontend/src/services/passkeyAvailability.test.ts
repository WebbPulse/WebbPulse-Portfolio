import { afterEach, describe, expect, it, vi } from 'vitest';

import { resetAvailabilityCache } from './availabilityCache';
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
