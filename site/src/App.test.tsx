import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import App from './App';

describe('App', () => {
  it('links every product to its live site', () => {
    render(<App />);
    const products = screen.getByRole('region', { name: 'Products' });
    expect(
      within(products).getByRole('link', { name: /standupless\.dev/ })
    ).toHaveAttribute('href', 'https://standupless.dev');
    expect(
      within(products).getByRole('link', { name: /carmodpicker\.com/ })
    ).toHaveAttribute('href', 'https://www.carmodpicker.com');
  });

  it('links the founder portfolio', () => {
    render(<App />);
    expect(
      screen.getByRole('link', { name: /portfolio\.webbpulse\.com/ })
    ).toHaveAttribute('href', 'https://portfolio.webbpulse.com');
  });

  it('offers email as the contact route', () => {
    render(<App />);
    const contact = screen.getByRole('region', { name: 'Contact' });
    expect(
      within(contact).getByRole('link', { name: 'hello@webbpulse.com' })
    ).toHaveAttribute('href', 'mailto:hello@webbpulse.com');
  });

  it('keeps em dashes out of the copy', () => {
    const { container } = render(<App />);
    expect(container.textContent).not.toMatch(/—/);
  });
});
