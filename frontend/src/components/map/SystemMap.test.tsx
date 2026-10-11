import { describe, expect, it } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { PublicFigure } from '../../services/api';
import { SystemMap } from './SystemMap';

function renderMap(figures = new Map<string, PublicFigure>()) {
  const view = render(
    <MemoryRouter>
      <SystemMap figures={figures} />
    </MemoryRouter>
  );
  const node = (id: string) => {
    const el = view.container.querySelector<HTMLElement>(
      `.map-node[data-node="${id}"]`
    );
    if (!el) throw new Error(`no node ${id}`);
    return el;
  };
  return { ...view, node };
}

describe('SystemMap', () => {
  it('links nodes to their case studies with a spoken description', () => {
    const { node } = renderMap();

    expect(node('standupless')).toHaveAttribute('href', '/work/standupless');
    expect(node('aws-org')).toHaveAttribute('href', '/work/aws-organisation');
    expect(node('standupless').getAttribute('aria-label')).toMatch(
      /^Standupless, Issue tracker\./
    );
  });

  it('gives one node a tab stop', () => {
    const { container } = renderMap();
    const stops = container.querySelectorAll('.map-node[tabindex="0"]');
    expect(stops).toHaveLength(1);
  });

  it('lights a hovered node and its connections and dims the rest', () => {
    const { node } = renderMap();

    fireEvent.mouseEnter(node('aws-org'));

    expect(node('aws-org')).toHaveAttribute('data-state', 'active');
    expect(node('artifacts')).toHaveAttribute('data-state', 'linked');
    expect(node('carmodpicker')).toHaveAttribute('data-state', 'dim');
  });

  it('moves focus with the arrow keys', () => {
    const { node } = renderMap();

    act(() => node('standupless').focus());
    fireEvent.keyDown(node('standupless'), { key: 'ArrowRight' });
    expect(node('carmodpicker')).toHaveFocus();

    fireEvent.keyDown(node('carmodpicker'), { key: 'End' });
    expect(node('aws-org')).toHaveFocus();
    expect(node('aws-org')).toHaveAttribute('tabindex', '0');
  });

  it('shows live figures on their nodes', () => {
    const figure: PublicFigure = {
      id: 'status-standupless',
      label: 'Standupless',
      value: 'up',
      as_of: '2026-10-10T12:00:00Z',
      source: 'health check',
    };
    renderMap(new Map([[figure.id, figure]]));

    expect(screen.getAllByText('Up').length).toBeGreaterThan(0);
  });

  it('renders the list view for narrow screens', () => {
    renderMap();
    expect(
      screen.getByRole('list', { name: 'System map as a list' })
    ).toBeInTheDocument();
  });
});
