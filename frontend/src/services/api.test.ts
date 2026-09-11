import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiService, identityOriginFrom } from './api';

const BASE = 'https://api.example.test/api/v1';

/**
 * The origin the identity routes answer on.
 *
 * Not `BASE`: identity mounts at the issuer's path directly on the host, so
 * `/api/auth/...` rather than `/api/v1/api/auth/...`.
 */
const ORIGIN = 'https://api.example.test';

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
    expect(response.error).toBe('Project not found');
  });

  it('reads the message out of the WebbPulse error envelope', async () => {
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
    expect(response.status).toBe(404);
    expect(response.requestId).toBe('0199a1f2-0000-7000-8000-000000000001');
  });

  it('logs the request id and status from the envelope on a failure', async () => {
    const consoleError = vi.spyOn(console, 'error');
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

    expect(consoleError).toHaveBeenCalledWith('API request failed:', {
      message: 'Internal server error.',
      status: 500,
      requestId: '0199a1f2-0000-7000-8000-000000000002',
    });
  });

  it('reports an error_code when the backend sends one', async () => {
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

      expect(response.status).toBe('authenticated');
      expect(service.isAuthenticated()).toBe(true);
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
      expect(url).toBe(`${ORIGIN}/api/auth/login`);
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
        .mockResolvedValueOnce(
          jsonResponse({ detail: 'expired' }, { status: 401 })
        )
        .mockResolvedValueOnce(tokenResponse('second-token'))
        .mockResolvedValueOnce(jsonResponse({ id: 1 }));

      const response = await service.getSiteContent();

      expect(response.error).toBeUndefined();
      expect(response.data).toEqual({ id: 1 });
      const urls = fetchMock.mock.calls.map(call => (call as [string])[0]);
      expect(urls[2]).toBe(`${ORIGIN}/api/auth/refresh`);
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

      expect(response).toEqual({
        status: 'failed',
        error: 'Email or password is incorrect.',
      });
      expect(service.isAuthenticated()).toBe(false);
    });

    it('reports an MFA challenge as its own result, carrying the ticket', async () => {
      fetchMock.mockResolvedValue(
        jsonResponse({ mfa_required: true, mfa_ticket: 't', factors: ['totp'] })
      );
      const service = new ApiService(BASE, 'identity');

      const response = await service.login({
        username: 'admin',
        password: 'secret',
      });

      expect(response).toEqual({ status: 'mfa-required', ticket: 't' });
      expect(service.isAuthenticated()).toBe(false);
    });

    it('exposes the same client the API refreshes through', () => {
      const service = new ApiService(BASE, 'identity');
      expect(service.getIdentityClient()).not.toBeNull();
    });

    it('exposes no auth client in bearer mode', () => {
      const service = new ApiService(BASE, 'bearer');
      expect(service.getIdentityClient()).toBeNull();
    });

    it('calls the identity routes on the origin rather than under /api/v1', async () => {
      fetchMock.mockResolvedValue(tokenResponse('memory-token'));
      const service = new ApiService(BASE, 'identity');

      await service.login({ username: 'admin', password: 'secret' });

      expect(callArgs().url).toBe('https://api.example.test/api/auth/login');
    });

    it('reports an MFA challenge, then finishes the login with a TOTP code', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({
          mfa_required: true,
          mfa_ticket: 't1',
          factors: ['totp'],
        })
      );
      const service = new ApiService(BASE, 'identity');

      const first = await service.login({
        username: 'admin',
        password: 'secret',
      });
      expect(first).toEqual({ status: 'mfa-required', ticket: 't1' });

      fetchMock.mockResolvedValueOnce(tokenResponse('memory-token'));
      const second = await service.completeTotp({
        ticket: 't1',
        code: '123456',
      });

      expect(second).toEqual({ status: 'authenticated' });
      expect(service.isAuthenticated()).toBe(true);

      const totpCall = fetchMock.mock.calls[1] as [string, RequestInit];
      expect(totpCall[0]).toBe('https://api.example.test/api/auth/login/totp');
      expect(JSON.parse(totpCall[1].body as string)).toEqual({
        mfa_ticket: 't1',
        code: '123456',
      });
    });

    it('refuses a TOTP completion in bearer mode rather than throwing', async () => {
      const service = new ApiService(BASE, 'bearer');

      const result = await service.completeTotp({ ticket: 't', code: '1' });

      expect(result.status).toBe('failed');
    });

    it('restores a session from the refresh cookie on load', async () => {
      fetchMock.mockResolvedValueOnce(tokenResponse('restored-token'));
      const service = new ApiService(BASE, 'identity');

      const restored = await service.restoreSession();

      expect(restored).toBe(true);
      expect(service.isAuthenticated()).toBe(true);
      expect(callArgs().url).toBe(`${ORIGIN}/api/auth/refresh`);
    });

    it('reports no session when the refresh cookie is missing or spent', async () => {
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ message: 'Unauthorized' }, { status: 401 })
      );
      const service = new ApiService(BASE, 'identity');

      const restored = await service.restoreSession();

      expect(restored).toBe(false);
      expect(service.isAuthenticated()).toBe(false);
    });

    it('sends the restored token as a bearer header on the next request', async () => {
      fetchMock.mockResolvedValueOnce(tokenResponse('restored-token'));
      const service = new ApiService(BASE, 'identity');
      await service.restoreSession();

      fetchMock.mockResolvedValueOnce(jsonResponse({ id: 1 }));
      await service.getSiteContent();

      const call = fetchMock.mock.calls[1] as [string, RequestInit];
      expect((call[1].headers as Headers).get('authorization')).toBe(
        'Bearer restored-token'
      );
    });

    it('notifies session-ended subscribers when a refresh on a 401 is refused', async () => {
      fetchMock.mockResolvedValueOnce(tokenResponse('memory-token'));
      const service = new ApiService(BASE, 'identity');
      await service.login({ username: 'admin', password: 'secret' });

      const ended = vi.fn();
      service.onSessionEnded(ended);

      // The write is refused, the refresh it triggers is refused too, so the
      // session is over rather than replayable.
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ message: 'Unauthorized' }, { status: 401 })
      );
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ message: 'Unauthorized' }, { status: 401 })
      );

      const response = await service.getSiteContent();

      expect(response.error).not.toBeNull();
      expect(ended).toHaveBeenCalledTimes(1);
      expect(service.isAuthenticated()).toBe(false);
    });

    it('stops notifying a session-ended subscriber once it unsubscribes', async () => {
      fetchMock.mockResolvedValueOnce(tokenResponse('memory-token'));
      const service = new ApiService(BASE, 'identity');
      await service.login({ username: 'admin', password: 'secret' });

      const ended = vi.fn();
      service.onSessionEnded(ended)();

      fetchMock.mockResolvedValueOnce(
        jsonResponse({ message: 'Unauthorized' }, { status: 401 })
      );
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ message: 'Unauthorized' }, { status: 401 })
      );
      await service.getSiteContent();

      expect(ended).not.toHaveBeenCalled();
    });

    it('reports the stored token rather than refreshing in bearer mode', async () => {
      localStorage.setItem('authToken', 'stored-token');
      const service = new ApiService(BASE, 'bearer');

      const restored = await service.restoreSession();

      expect(restored).toBe(true);
      expect(fetchMock).not.toHaveBeenCalled();
    });
  });

  describe('identityOriginFrom', () => {
    it('strips the API path back to the origin', () => {
      expect(identityOriginFrom('https://api.example.test/api/v1')).toBe(
        'https://api.example.test'
      );
    });

    it('returns the input unchanged when it will not parse', () => {
      expect(identityOriginFrom('not a url')).toBe('not a url');
    });
  });
});
