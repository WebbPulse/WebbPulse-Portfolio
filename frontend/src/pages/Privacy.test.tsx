import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Privacy } from './Privacy';
import * as hooks from '../hooks';

// The page is static prose, so what is worth pinning down is the part that is
// not: the contact address comes from site content rather than being written
// into the copy, and the page has to still name an address when that request
// has not resolved. A policy published for Google's OAuth consent screen that
// renders without a contact line would fail the review it exists to pass.

/** Stubs `useSiteContent` with the shape the page reads off it. */
function stubSiteContent(data: { email?: string | null } | null) {
  vi.spyOn(hooks, 'useSiteContent').mockReturnValue({
    data,
    loading: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof hooks.useSiteContent>);
}

function renderPage() {
  return render(
    <MemoryRouter>
      <Privacy />
    </MemoryRouter>
  );
}

describe('Privacy', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the policy heading and its effective date', () => {
    stubSiteContent({ email: 'tyler@webbpulse.com' });
    renderPage();

    expect(
      screen.getByRole('heading', { name: /privacy policy/i, level: 1 })
    ).toBeInTheDocument();
    expect(screen.getByText(/September 10, 2026/)).toBeInTheDocument();
  });

  it('uses the contact address from site content', () => {
    stubSiteContent({ email: 'hello@example.com' });
    renderPage();

    const links = screen.getAllByRole('link', { name: 'hello@example.com' });
    expect(links.length).toBeGreaterThan(0);
    expect(links[0]).toHaveAttribute('href', 'mailto:hello@example.com');
  });

  it('falls back to the site address when site content has not loaded', () => {
    stubSiteContent(null);
    renderPage();

    const links = screen.getAllByRole('link', { name: 'tyler@webbpulse.com' });
    expect(links[0]).toHaveAttribute('href', 'mailto:tyler@webbpulse.com');
  });
});
