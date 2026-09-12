import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { NotFound } from './NotFound';
import * as hooks from '../hooks';

/** Stubs `useSiteContent` so the shared footer can render without the API. */
function stubSiteContent() {
  vi.spyOn(hooks, 'useSiteContent').mockReturnValue({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  });
}

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
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders for a URL that matches no route', () => {
    stubSiteContent();
    renderAt('/no-such-page');

    expect(
      screen.getByRole('heading', { name: /page not found/i, level: 1 })
    ).toBeInTheDocument();
  });

  it('offers a link back to home', () => {
    stubSiteContent();
    renderAt('/deep/unknown/path');

    const link = screen.getByRole('link', { name: /back to home/i });
    expect(link).toHaveAttribute('href', '/');
  });

  it('leaves a known route alone', () => {
    stubSiteContent();
    renderAt('/');

    expect(screen.getByText('home page')).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: /page not found/i })
    ).not.toBeInTheDocument();
  });
});
