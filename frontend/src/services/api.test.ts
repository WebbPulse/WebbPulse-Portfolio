import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiService } from './api';

// These tests cover the contract this service exposes: @webbpulse/api-client
// rejects on a non 2xx, and every call site in this application reads a
// `{ data, error }` envelope instead. The conversion is now the package's
// `createEnvelopeClient` rather than a helper in this file, so what is worth
// pinning down here is that wiring it up preserved the shapes those call sites
// depend on. The transport and the envelope conversion are tested in the
// package itself; these are the application's end of the contract.

const BASE = 'https://api.example.test/api/v1';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  });
}

describe('ApiService', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  /** The single fetch call the test made, with the loose mock types narrowed. */
  function callArgs(): { url: string; init: RequestInit; headers: Headers } {
    const call = fetchMock.mock.calls[0] as [string, RequestInit] | undefined;
    if (call === undefined) {
      throw new Error('fetch was not called');
    }
    const [url, init] = call;
    return { url, init, headers: init.headers as Headers };
  }

  beforeEach(() => {
    localStorage.clear();
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('returns the parsed body in the data field on success', async () => {
    fetchMock.mockResolvedValue(jsonResponse([{ id: 1, title: 'One' }]));
    const service = new ApiService(BASE);

    const response = await service.getProjects();

    expect(response.error).toBeUndefined();
    expect(response.data).toEqual([{ id: 1, title: 'One' }]);
  });

  it('converts a rejection into the error field rather than throwing', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: 'Project not found' }, { status: 404 })
    );
    const service = new ApiService(BASE);

    const response = await service.getProject(99);

    expect(response.data).toBeNull();
    // formatApiErrorMessage unpacks the FastAPI detail field.
    expect(response.error).toBe('Project not found');
  });

  it('reads the message out of the WebbPulse error envelope', async () => {
    // The shape every WebbPulse backend renders, built by `error_body` in the
    // shared Python package. `message` is the field written for a caller to
    // read, so it is the one that has to reach the UI.
    // The backend writes the id into both the body and the X-Request-ID
    // header, from the same middleware value, so the fixture carries both.
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          success: false,
          status: 404,
          message: 'Blog post not found.',
          request_id: '0199a1f2-0000-7000-8000-000000000001',
        },
        {
          status: 404,
          headers: {
            'content-type': 'application/json',
            'x-request-id': '0199a1f2-0000-7000-8000-000000000001',
          },
        }
      )
    );
    const service = new ApiService(BASE);

    const response = await service.getBlogPostBySlug('missing');

    expect(response.data).toBeNull();
    expect(response.error).toBe('Blog post not found.');
    // The envelope carries these alongside the message now. The hand rolled
    // adapter dropped both, so a failure could not be joined to its trace.
    // Note the envelope's own requestId is read from the response header, not
    // from the body: getWebbPulseError is what prefers the body's request_id,
    // which is why the log line above still has an id for a body that crossed
    // a proxy that dropped the header.
    expect(response.status).toBe(404);
    expect(response.requestId).toBe('0199a1f2-0000-7000-8000-000000000001');
  });

  it('logs the request id and status from the envelope on a failure', async () => {
    const consoleError = vi.spyOn(console, 'error');
    // A 500 on a GET is retried by the client, and a Response body can only be
    // read once, so the mock builds a fresh one per attempt rather than
    // handing back the same object.
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse(
          {
            success: false,
            status: 500,
            message: 'Internal server error.',
            request_id: '0199a1f2-0000-7000-8000-000000000002',
          },
          { status: 500 }
        )
      )
    );
    const service = new ApiService(BASE);

    await service.getSiteContent();

    // getWebbPulseError flattens the snake cased body, so the log line carries
    // the id that joins it to CloudWatch without this file parsing the body.
    expect(consoleError).toHaveBeenCalledWith('API request failed:', {
      message: 'Internal server error.',
      status: 500,
      requestId: '0199a1f2-0000-7000-8000-000000000002',
    });
  });

  it('reports an error_code when the backend sends one', async () => {
    // Portfolio's backend has not opted into `error_codes` yet, so this pins
    // the branch that will start firing when it does, rather than leaving the
    // first consumer of a code to discover the plumbing was never wired.
    const consoleError = vi.spyOn(console, 'error');
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          success: false,
          status: 409,
          message: 'That slug is already taken.',
          request_id: '0199a1f2-0000-7000-8000-000000000003',
          error_code: 'CONFLICT',
        },
        { status: 409 }
      )
    );
    const service = new ApiService(BASE);

    const response = await service.createCategory({ name: 'Ops', slug: 'ops' });

    expect(response.error).toBe('That slug is already taken.');
    expect(consoleError).toHaveBeenCalledWith('API request failed:', {
      message: 'That slug is already taken.',
      status: 409,
      errorCode: 'CONFLICT',
      requestId: '0199a1f2-0000-7000-8000-000000000003',
    });
  });

  it('converts a network failure into the error field', async () => {
    // fetch rejecting is what a browser does when the request never reached the
    // server. There is no envelope to read, so the envelope has no status and
    // the message is whatever the client raised.
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    const service = new ApiService(BASE);

    const response = await service.getProjects();

    expect(response.data).toBeNull();
    expect(response.error).toBeTruthy();
    expect(response.status).toBeUndefined();
  });

  it('unpacks a FastAPI validation error array into one line', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          detail: [
            { loc: ['body', 'title'], msg: 'field required', type: 'missing' },
          ],
        },
        { status: 422 }
      )
    );
    const service = new ApiService(BASE);

    const response = await service.getSiteContent();

    expect(response.error).toBe('field required');
  });

  it('sends the stored token as a bearer header', async () => {
    localStorage.setItem('authToken', 'stored-token');
    fetchMock.mockResolvedValue(jsonResponse({ id: 1 }));
    const service = new ApiService(BASE);

    await service.getSiteContent();

    expect(callArgs().headers.get('authorization')).toBe('Bearer stored-token');
  });

  it('stores the token on login and reports authentication', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ access_token: 'fresh-token', token_type: 'bearer' })
    );
    const service = new ApiService(BASE);
    expect(service.isAuthenticated()).toBe(false);

    await service.login({ username: 'admin', password: 'secret' });

    expect(localStorage.getItem('authToken')).toBe('fresh-token');
    expect(service.isAuthenticated()).toBe(true);
  });

  it('clears the token on logout', () => {
    localStorage.setItem('authToken', 'stored-token');
    const service = new ApiService(BASE);
    expect(service.isAuthenticated()).toBe(true);

    service.logout();

    expect(localStorage.getItem('authToken')).toBeNull();
    expect(service.isAuthenticated()).toBe(false);
  });

  it('sends the featured filter as a query parameter, keeping the trailing slash', async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    const service = new ApiService(BASE);

    await service.getProjects(true);

    // The previous implementation built `/projects?featured_only=true/`, which
    // put the trailing slash inside the query string.
    expect(callArgs().url).toBe(`${BASE}/projects/?featured_only=true`);
  });

  it('JSON encodes a body and sets the content type', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 7 }));
    const service = new ApiService(BASE);

    await service.createCategory({ name: 'Ops', slug: 'ops' });

    const { init, headers } = callArgs();
    expect(init.body).toBe(JSON.stringify({ name: 'Ops', slug: 'ops' }));
    expect(headers.get('content-type')).toBe('application/json');
  });

  it('includes credentials so the staging access gate cookies are sent', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}));
    const service = new ApiService(BASE);

    await service.getSiteContent();

    expect(callArgs().init.credentials).toBe('include');
  });

  // The identity mode, which is written and typed today and switched on by
  // configuration once the backend serves the routes it calls. These tests are
  // what make it a real path rather than an untested branch: the wiring is
  // exercised against a stubbed fetch, so a change that breaks it fails here
  // and not on the day of the cutover.
  describe('identity mode', () => {
    /** The token response the standard's login and refresh routes answer. */
    function tokenResponse(token: string, expiresIn = 900): Response {
      return jsonResponse({ access_token: token, expires_in: expiresIn });
    }

    it('signs in through the auth client and holds no token in localStorage', async () => {
      fetchMock.mockResolvedValue(tokenResponse('memory-token'));
      const service = new ApiService(BASE, 'identity');

      const response = await service.login({
        username: 'admin@example.test',
        password: 'secret',
      });

      expect(response.error).toBeUndefined();
      expect(response.data?.access_token).toBe('memory-token');
      expect(service.isAuthenticated()).toBe(true);
      // The point of section 7.1: nothing a script can read back after a
      // reload.
      expect(localStorage.getItem('authToken')).toBeNull();
      expect(localStorage.length).toBe(0);
    });

    it('posts the username as the email the identity login expects', async () => {
      fetchMock.mockResolvedValue(tokenResponse('memory-token'));
      const service = new ApiService(BASE, 'identity');

      await service.login({
        username: 'admin@example.test',
        password: 'secret',
      });

      const { url, init } = callArgs();
      expect(url).toBe(`${BASE}/api/auth/login`);
      expect(init.body).toBe(
        JSON.stringify({ email: 'admin@example.test', password: 'secret' })
      );
    });

    it('sends the in memory token as a bearer header on an ordinary request', async () => {
      fetchMock.mockResolvedValueOnce(tokenResponse('memory-token'));
      const service = new ApiService(BASE, 'identity');
      await service.login({ username: 'admin', password: 'secret' });

      fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1 }));
      await service.getSiteContent();

      const call = fetchMock.mock.calls[1] as [string, RequestInit];
      expect((call[1].headers as Headers).get('authorization')).toBe(
        'Bearer memory-token'
      );
    });

    it('refreshes once on a 401 and replays the request', async () => {
      fetchMock.mockResolvedValueOnce(tokenResponse('first-token'));
      const service = new ApiService(BASE, 'identity');
      await service.login({ username: 'admin', password: 'secret' });

      fetchMock
        // The original request, with an expired token.
        .mockResolvedValueOnce(
          jsonResponse({ detail: 'expired' }, { status: 401 })
        )
        // The refresh, which rotates the cookie and issues a new token.
        .mockResolvedValueOnce(tokenResponse('second-token'))
        // The single replay.
        .mockResolvedValueOnce(jsonResponse({ id: 1 }));

      const response = await service.getSiteContent();

      expect(response.error).toBeUndefined();
      expect(response.data).toEqual({ id: 1 });
      const urls = fetchMock.mock.calls.map(call => (call as [string])[0]);
      expect(urls[2]).toBe(`${BASE}/api/auth/refresh`);
      // Exactly one refresh, and the replay carries the new token.
      expect(
        urls.filter(url => url.endsWith('/api/auth/refresh'))
      ).toHaveLength(1);
      const replay = fetchMock.mock.calls[3] as [string, RequestInit];
      expect((replay[1].headers as Headers).get('authorization')).toBe(
        'Bearer second-token'
      );
    });

    it('reports a failed sign in through the error field rather than throwing', async () => {
      fetchMock.mockResolvedValue(
        jsonResponse(
          { message: 'Email or password is incorrect.' },
          { status: 401 }
        )
      );
      const service = new ApiService(BASE, 'identity');

      const response = await service.login({
        username: 'admin',
        password: 'wrong',
      });

      expect(response.data).toBeNull();
      expect(response.error).toBe('Email or password is incorrect.');
      expect(service.isAuthenticated()).toBe(false);
    });

    it('reports an MFA challenge as a failed sign in, since there is no form for it yet', async () => {
      fetchMock.mockResolvedValue(
        jsonResponse({ mfa_required: true, mfa_ticket: 't', factors: ['totp'] })
      );
      const service = new ApiService(BASE, 'identity');

      const response = await service.login({
        username: 'admin',
        password: 'secret',
      });

      expect(response.data).toBeNull();
      expect(response.error).toContain('second factor');
    });

    it('exposes the same client the API refreshes through', () => {
      const service = new ApiService(BASE, 'identity');
      expect(service.getAuthClient()).not.toBeNull();
    });

    it('exposes no auth client in bearer mode', () => {
      const service = new ApiService(BASE, 'bearer');
      expect(service.getAuthClient()).toBeNull();
    });
  });
});
