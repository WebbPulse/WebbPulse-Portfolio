import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { NotFound } from './NotFound';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<p>home page</p>} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('NotFound', () => {
  it('renders for a URL that matches no route', () => {
    renderAt('/no-such-page');

    expect(
      screen.getByRole('heading', { name: /page not found/i, level: 1 })
    ).toBeInTheDocument();
  });

  it('offers a link back to home', () => {
    renderAt('/deep/unknown/path');

    const link = screen.getByRole('link', { name: /back to home/i });
    expect(link).toHaveAttribute('href', '/');
  });

  it('leaves a known route alone', () => {
    renderAt('/');

    expect(screen.getByText('home page')).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: /page not found/i })
    ).not.toBeInTheDocument();
  });
});
