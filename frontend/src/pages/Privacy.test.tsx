import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Privacy } from './Privacy';
import { getSiteContent } from '../content';

function renderPage() {
  return render(
    <MemoryRouter>
      <Privacy />
    </MemoryRouter>
  );
}

describe('Privacy', () => {
  it('renders the policy heading and its effective date', () => {
    renderPage();

    expect(
      screen.getByRole('heading', { name: /privacy policy/i, level: 1 })
    ).toBeInTheDocument();
    expect(screen.getByText(/October 10, 2026/)).toBeInTheDocument();
  });

  it('uses the contact address from the committed site content', () => {
    const email = getSiteContent().email ?? 'tyler@webbpulse.com';
    renderPage();

    const links = screen.getAllByRole('link', { name: email });
    expect(links.length).toBeGreaterThan(0);
    expect(links[0]).toHaveAttribute('href', `mailto:${email}`);
  });
});
