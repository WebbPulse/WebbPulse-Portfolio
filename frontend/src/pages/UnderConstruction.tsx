/** The holding page shown when the site is switched off. */
export function UnderConstruction() {
  return (
    <main
      id="main"
      className="drawing-grid flex min-h-screen flex-col items-center justify-center px-4 text-ink"
    >
      <div className="relative w-full max-w-md border border-line bg-paper-raised px-6 py-10 sm:px-10">
        <p className="mono-label">portfolio.webbpulse.com</p>
        <h1 className="mt-4 text-4xl font-semibold tracking-[-0.02em] text-ink">
          Under construction
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-ink-muted">
          The site is getting a refresh. Check back soon.
        </p>
        <p className="mt-8 border-t border-line pt-6 text-sm text-ink-muted">
          In the meantime, reach out at{' '}
          <a href="mailto:tyler@webbpulse.com" className="ink-link">
            tyler@webbpulse.com
          </a>
        </p>
      </div>
    </main>
  );
}
