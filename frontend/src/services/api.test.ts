import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiService } from './api';

// These tests cover the adapter this service is: @webbpulse/api-client rejects
// on a non 2xx, and every call site in this application reads the
// `{ data, error }` envelope instead. What is worth pinning down is the
// conversion between the two, not the transport, which the shared package
// tests itself.

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
});
