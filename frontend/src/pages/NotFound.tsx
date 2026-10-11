import React from 'react';
import { Link } from 'react-router-dom';
import { PublicShell } from '../components/layout';
import { MonoLabel, RegistrationMarks, Sheet } from '../components/drawing';

/** The catch-all page for a URL that matches no route. */
export const NotFound: React.FC = () => (
  <PublicShell>
    <main id="main" className="flex-1" data-testid="page-not-found">
      <Sheet className="py-20 sm:py-28">
        <div className="relative mx-auto max-w-2xl border border-line bg-paper-raised/70 px-6 py-12 sm:px-12">
          <RegistrationMarks />
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-accent">404</span>
            <span className="h-3 w-px bg-line-strong" aria-hidden="true" />
            <MonoLabel>Sheet missing</MonoLabel>
          </div>
          <h1 className="mt-5 text-4xl font-semibold tracking-[-0.02em] text-ink sm:text-5xl">
            Page not found
          </h1>
          <p className="mt-5 leading-relaxed text-ink-muted">
            The page you asked for does not exist, or it has moved somewhere
            else on this site.
          </p>
          <Link
            to="/"
            className="mt-10 inline-flex items-center gap-2 border border-ink bg-ink px-5 py-3 text-sm font-medium text-paper transition-colors hover:border-accent hover:bg-accent"
          >
            <span aria-hidden="true">←</span> Back to home
          </Link>
        </div>
      </Sheet>
    </main>
  </PublicShell>
);

export default NotFound;
