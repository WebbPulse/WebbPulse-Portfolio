import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { PublicFigure } from '../../services/api';
import { FiguresStrip } from './FiguresStrip';
import { asOfTime, figureValue, latestAsOf } from './figures';

const figure: PublicFigure = {
  id: 'status-standupless',
  label: 'Standupless',
  value: 'up',
  as_of: '2026-10-10T09:05:00Z',
  source: 'health check',
};

describe('FiguresStrip', () => {
  it('renders nothing without figures', () => {
    const { container } = render(<FiguresStrip figures={new Map()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders each figure with its read time', () => {
    const release: PublicFigure = {
      id: 'release-webbpulse-python',
      label: 'webbpulse',
      value: '0.89.0',
      as_of: '2026-10-09T22:44:00Z',
      source: 'CodeArtifact',
      url: 'https://example.com/release',
    };
    render(
      <FiguresStrip
        figures={
          new Map([
            [release.id, release],
            [figure.id, figure],
          ])
        }
      />
    );
    expect(screen.getByTestId('live-figures')).toBeInTheDocument();
    expect(screen.getByText('Up')).toBeInTheDocument();
    expect(screen.getByText('0.89.0')).toBeInTheDocument();
    expect(screen.getByText(/09:05 UTC/)).toBeInTheDocument();
  });
});

describe('figure helpers', () => {
  it('spells out statuses and formats the read time', () => {
    expect(figureValue({ ...figure, value: 'down' })).toBe('Down');
    expect(figureValue({ ...figure, id: 'release-x', value: '1.2.3' })).toBe(
      '1.2.3'
    );
    expect(asOfTime('2026-10-10T23:59:00Z')).toBe('23:59');
    expect(asOfTime('not a date')).toBe('');
  });

  it('takes the newest read time across figures', () => {
    expect(
      latestAsOf([
        { ...figure, as_of: '2026-10-09T22:44:00Z' },
        { ...figure, as_of: 'not a date' },
        { ...figure, as_of: '2026-10-10T09:05:00Z' },
      ])
    ).toBe('2026-10-10T09:05:00Z');
    expect(latestAsOf([])).toBe('');
  });
});
