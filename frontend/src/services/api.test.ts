import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiService } from './api';

const BASE = 'https://api.example.test/api/v1';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  });
}

describe('ApiService', () => {
  let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;

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
    fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('reads the public figures from the public route', async () => {
    const figures = [
      {
        id: 'release',
        label: 'Latest release',
        value: 'v1.0.0',
        as_of: '2026-10-10T00:00:00Z',
        source: 'github',
      },
    ];
    fetchMock.mockResolvedValue(jsonResponse({ figures }));
    const service = new ApiService(BASE);

    const response = await service.getPublicFigures();

    expect(callArgs().url).toBe(`${BASE}/public/figures`);
    expect(response.error).toBeUndefined();
    expect(response.data).toEqual({ figures });
  });

  it('sends no bearer header, since every remaining route is anonymous', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ figures: [] }));
    const service = new ApiService(BASE);

    await service.getPublicFigures();

    expect(callArgs().headers.get('authorization')).toBeNull();
  });

  it('includes credentials so the staging access gate cookies are sent', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ figures: [] }));
    const service = new ApiService(BASE);

    await service.getPublicFigures();

    expect(callArgs().init.credentials).toBe('include');
  });

  it('returns the envelope error without logging on a failure', async () => {
    const consoleError = vi.spyOn(console, 'error');
    const consoleWarn = vi.spyOn(console, 'warn');
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

    const response = await service.getPublicFigures();

    expect(response.data).toBeNull();
    expect(response.error).toBe('Internal server error.');
    expect(consoleError).not.toHaveBeenCalled();
    expect(consoleWarn).not.toHaveBeenCalled();
  });

  it('converts a network failure into the error field', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    const service = new ApiService(BASE);

    const response = await service.getPublicFigures();

    expect(response.data).toBeNull();
    expect(response.error).toBeTruthy();
    expect(response.status).toBeUndefined();
  });
});
