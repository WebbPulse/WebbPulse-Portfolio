import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { CaseStudy } from './CaseStudy';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/work/:slug" element={<CaseStudy />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('CaseStudy', () => {
  beforeEach(() => {
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
  });

  it('merges the write-up with the project entry', () => {
    renderAt('/work/standupless');

    expect(screen.getByTestId('page-case-study')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 1, name: 'Standupless' })
    ).toBeInTheDocument();
    expect(screen.getByText('22 DynamoDB tables')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Source on GitHub' })
    ).toHaveAttribute('href', 'https://github.com/WebbPulse/Standupless');
    expect(
      screen.getByRole('heading', { name: 'Problem' })
    ).toBeInTheDocument();
    expect(document.title).toBe('Standupless | Tyler Webb');
  });

  it('renders from frontmatter alone', () => {
    renderAt('/work/platform-packages');

    expect(
      screen.getByRole('heading', {
        level: 1,
        name: 'Shared platform packages and modules',
      })
    ).toBeInTheDocument();
    expect(screen.getByText(/Sole software engineer/)).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Source on GitHub' })
    ).not.toBeInTheDocument();
  });

  it('renders from the project alone', () => {
    renderAt('/work/webbpulse-portfolio');

    expect(
      screen.getByRole('heading', { level: 1, name: 'WebbPulse Portfolio' })
    ).toBeInTheDocument();
    expect(screen.getByText('Full write-up in progress.')).toBeInTheDocument();
  });

  it('shows a not found state under the same test id', () => {
    renderAt('/work/no-such-thing');

    expect(screen.getByTestId('page-case-study')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 1, name: 'Case study not found' })
    ).toBeInTheDocument();
    expect(document.title).toBe('Case study not found | Tyler Webb');
  });
});
