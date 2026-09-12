import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ErrorBoundary from './ErrorBoundary';

/** A child that throws on its first render pass. */
function Boom(): React.ReactNode {
  throw new Error('boom');
}

function renderBoundary(children: React.ReactNode) {
  return render(
    <MemoryRouter>
      <ErrorBoundary>{children}</ErrorBoundary>
    </MemoryRouter>
  );
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders its children when nothing throws', () => {
    renderBoundary(<p>all good</p>);

    expect(screen.getByText('all good')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders the fallback when a child throws', () => {
    renderBoundary(<Boom />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /something went wrong/i, level: 1 })
    ).toBeInTheDocument();
  });

  it('offers a reload button and a link back to home', () => {
    renderBoundary(<Boom />);

    expect(
      screen.getByRole('button', { name: /reload the page/i })
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to home/i })).toHaveAttribute(
      'href',
      '/'
    );
  });

  it('reports the error', () => {
    renderBoundary(<Boom />);

    expect(console.error).toHaveBeenCalledWith(
      'Unhandled render error',
      expect.objectContaining({ message: 'boom' }),
      expect.anything()
    );
  });
});
