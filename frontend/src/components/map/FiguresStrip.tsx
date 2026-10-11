import React from 'react';
import type { PublicFigure } from '../../services/api';
import { LiveDot } from '../drawing';
import { asOfTime, figureValue } from './figures';

/**
 * The strip of live figures under the map: latest releases and site status.
 *
 * Renders nothing at all until figures arrive, so a failed or empty fetch
 * leaves no trace on the page.
 */
export const FiguresStrip: React.FC<{ figures: Map<string, PublicFigure> }> = ({
  figures,
}) => {
  if (figures.size === 0) return null;
  const list = [...figures.values()];
  const stamp = asOfTime(list[0]?.as_of ?? '');
  return (
    <section
      aria-label="Live figures"
      data-testid="live-figures"
      className="mt-8 border-t border-line pt-3"
    >
      <div className="mb-3 flex items-center gap-2">
        <LiveDot />
        <span className="mono-label text-live-ink">Live</span>
        {stamp && <span className="mono-label">Read {stamp} UTC</span>}
      </div>
      <dl className="grid grid-cols-2 border-l border-t border-line sm:grid-cols-3 lg:grid-cols-6">
        {list.map((figure) => {
          const value = figureValue(figure);
          return (
            <div
              key={figure.id}
              className="min-w-0 border-b border-r border-line px-3 py-2.5"
            >
              <dt className="mono-label truncate">{figure.label}</dt>
              <dd className="mt-1 truncate font-mono text-sm text-ink">
                {figure.url ? (
                  <a
                    href={figure.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ink-link"
                  >
                    {value}
                  </a>
                ) : (
                  value
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
};

export default FiguresStrip;
