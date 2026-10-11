import { useEffect, useState } from 'react';
import { apiService, type PublicFigure } from '../services/api';

/** How long the figures request may take before the strip gives up. */
const FIGURES_TIMEOUT_MS = 6000;

/** True when `value` is a non-empty string. */
const isText = (value: unknown): value is string =>
  typeof value === 'string' && value.length > 0;

/**
 * The well-formed figures in a `GET /public/figures` body.
 *
 * Anything that is not an object with a `figures` array yields an empty list,
 * and each figure missing a required field is dropped.
 */
export function parseFigures(body: unknown): PublicFigure[] {
  if (typeof body !== 'object' || body === null) return [];
  const list: unknown = (body as { figures?: unknown }).figures;
  if (!Array.isArray(list)) return [];
  const figures: PublicFigure[] = [];
  for (const item of list as unknown[]) {
    if (typeof item !== 'object' || item === null) continue;
    const row = item as Record<string, unknown>;
    const { id, label, value, as_of: asOf, source, url } = row;
    if (!isText(id) || !isText(label) || !isText(value)) continue;
    const figure: PublicFigure = {
      id,
      label,
      value,
      as_of: isText(asOf) ? asOf : '',
      source: isText(source) ? source : '',
    };
    if (isText(url)) figure.url = url;
    figures.push(figure);
  }
  return figures;
}

/** The slice of the API service the figures fetch needs. */
export interface FiguresSource {
  getPublicFigures: () => Promise<{ data: unknown }>;
}

/**
 * Fetches the live public figures once through the API service.
 *
 * A failed request, a malformed body or no answer within a few seconds all
 * give an empty list, so the strip simply stays hidden.
 */
export async function fetchFigures(
  source: FiguresSource = apiService,
  timeoutMs: number = FIGURES_TIMEOUT_MS
): Promise<PublicFigure[]> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<PublicFigure[]>((resolve) => {
    timer = setTimeout(() => resolve([]), timeoutMs);
  });
  const request = source
    .getPublicFigures()
    .then((response) => parseFigures(response.data))
    .catch((): PublicFigure[] => []);
  try {
    return await Promise.race([request, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

/** The live figures by id, empty until they arrive or when the fetch fails. */
export function useLiveFigures(): Map<string, PublicFigure> {
  const [figures, setFigures] = useState<Map<string, PublicFigure>>(
    () => new Map()
  );

  useEffect(() => {
    let active = true;
    void fetchFigures().then((list) => {
      if (active && list.length) {
        setFigures(new Map(list.map((figure) => [figure.id, figure])));
      }
    });
    return () => {
      active = false;
    };
  }, []);

  return figures;
}
