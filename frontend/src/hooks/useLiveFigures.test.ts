import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchFigures, parseFigures } from './useLiveFigures';

const figure = {
  id: 'status-standupless',
  label: 'Standupless',
  value: 'up',
  as_of: '2026-10-10T12:00:00Z',
  source: 'health check',
};

describe('parseFigures', () => {
  it('keeps well-formed figures and drops the rest', () => {
    expect(
      parseFigures({
        figures: [
          figure,
          { ...figure, id: 'release-x', url: 'https://example.com' },
          { id: 'no-label', value: '1' },
          'junk',
          null,
        ],
      })
    ).toEqual([
      figure,
      { ...figure, id: 'release-x', url: 'https://example.com' },
    ]);
  });

  it('returns an empty list for a malformed body', () => {
    expect(parseFigures(null)).toEqual([]);
    expect(parseFigures({ figures: 'nope' })).toEqual([]);
    expect(parseFigures('text')).toEqual([]);
  });
});

describe('fetchFigures', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('parses the body the API service returns', async () => {
    const source = {
      getPublicFigures: () => Promise.resolve({ data: { figures: [figure] } }),
    };
    await expect(fetchFigures(source)).resolves.toEqual([figure]);
  });

  it('gives an empty list when the request fails', async () => {
    const source = {
      getPublicFigures: () => Promise.reject(new Error('offline')),
    };
    await expect(fetchFigures(source)).resolves.toEqual([]);
  });

  it('gives an empty list for an error envelope', async () => {
    const source = { getPublicFigures: () => Promise.resolve({ data: null }) };
    await expect(fetchFigures(source)).resolves.toEqual([]);
  });

  it('gives up after the timeout', async () => {
    vi.useFakeTimers();
    const source = {
      getPublicFigures: () => new Promise<{ data: unknown }>(() => undefined),
    };
    const result = fetchFigures(source, 1000);
    await vi.advanceTimersByTimeAsync(1000);
    await expect(result).resolves.toEqual([]);
  });
});
