import React from 'react';

/** Props shared by the drawing primitives. */
interface DrawingProps {
  className?: string;
  children?: React.ReactNode;
}

/** A small uppercase mono annotation, the way a drawing labels its parts. */
export const MonoLabel: React.FC<
  DrawingProps & { as?: 'span' | 'p' | 'div' | 'dt' | 'dd' | 'h2' }
> = ({ as: Tag = 'span', className = '', children }) => (
  <Tag className={`mono-label ${className}`}>{children}</Tag>
);

/** One crosshair registration mark, drawn at a corner of a framed area. */
const Mark: React.FC<{ className: string }> = ({ className }) => (
  <svg
    className={`absolute h-3 w-3 text-line-strong ${className}`}
    viewBox="0 0 12 12"
    fill="none"
    stroke="currentColor"
    strokeWidth="1"
    aria-hidden="true"
  >
    <path d="M6 0v12M0 6h12" />
  </svg>
);

/**
 * Corner registration marks for a relatively positioned parent.
 *
 * Purely decorative, so it is hidden from assistive technology.
 */
export const RegistrationMarks: React.FC<{ inset?: 'edge' | 'outside' }> = ({
  inset = 'outside',
}) => {
  const corners =
    inset === 'outside'
      ? [
          '-top-1.5 -left-1.5',
          '-top-1.5 -right-1.5',
          '-bottom-1.5 -left-1.5',
          '-bottom-1.5 -right-1.5',
        ]
      : [
          'top-1.5 left-1.5',
          'top-1.5 right-1.5',
          'bottom-1.5 left-1.5',
          'bottom-1.5 right-1.5',
        ];
  return (
    <span aria-hidden="true" className="pointer-events-none">
      {corners.map((corner) => (
        <Mark key={corner} className={corner} />
      ))}
    </span>
  );
};

/** A horizontal dimension line with end ticks and a mono label in the gap. */
export const DimensionLine: React.FC<{ label: string; className?: string }> = ({
  label,
  className = '',
}) => (
  <div
    aria-hidden="true"
    className={`flex items-center gap-3 text-line-strong ${className}`}
  >
    <span className="h-2.5 w-px bg-current" />
    <span className="h-px flex-1 bg-current" />
    <span className="mono-label whitespace-nowrap">{label}</span>
    <span className="h-px flex-1 bg-current" />
    <span className="h-2.5 w-px bg-current" />
  </div>
);

/** One labelled cell of a {@link TitleBlock}. */
export interface TitleBlockRow {
  label: string;
  value: React.ReactNode;
}

/**
 * The bordered grid in the corner of an engineering drawing.
 *
 * Rendered as a description list so each value keeps its label for screen
 * readers.
 */
export const TitleBlock: React.FC<{
  rows: TitleBlockRow[];
  className?: string;
  columns?: 2 | 3 | 4;
}> = ({ rows, className = '', columns = 2 }) => {
  const cols =
    columns === 4
      ? 'sm:grid-cols-2 lg:grid-cols-4'
      : columns === 3
        ? 'sm:grid-cols-3'
        : 'sm:grid-cols-2';
  return (
    <dl
      className={`grid grid-cols-1 ${cols} border-l border-t border-line ${className}`}
    >
      {rows.map((row) => (
        <div
          key={row.label}
          className="border-b border-r border-line px-3 py-2.5 min-w-0"
        >
          <dt className="mono-label">{row.label}</dt>
          <dd className="mt-1 text-sm text-ink truncate">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
};

/** The page width and gutters every sheet of the site shares. */
export const Sheet: React.FC<DrawingProps> = ({ className = '', children }) => (
  <div className={`mx-auto w-full max-w-6xl px-4 sm:px-8 ${className}`}>
    {children}
  </div>
);

/**
 * A numbered section heading: sheet index, label, title and a hairline rule.
 *
 * The index and label read like a drawing's sheet reference.
 */
export const SectionHeading: React.FC<{
  index: string;
  label: string;
  title: React.ReactNode;
  id?: string;
  aside?: React.ReactNode;
  children?: React.ReactNode;
}> = ({ index, label, title, id, aside, children }) => (
  <header className="mb-10 sm:mb-14">
    <div className="flex items-center gap-3 border-b border-line pb-3">
      <span className="font-mono text-xs text-accent tabular-nums">
        {index}
      </span>
      <span className="h-3 w-px bg-line-strong" aria-hidden="true" />
      <MonoLabel>{label}</MonoLabel>
      {aside && <div className="ml-auto">{aside}</div>}
    </div>
    <h2
      id={id}
      className="mt-6 max-w-3xl text-3xl sm:text-4xl font-semibold tracking-tight text-ink"
    >
      {title}
    </h2>
    {children && (
      <p className="mt-4 max-w-2xl text-base sm:text-lg leading-relaxed text-ink-muted">
        {children}
      </p>
    )}
  </header>
);

/**
 * The amber dot that marks a live value. Amber means live and nothing else on
 * this site, so only use it beside data that is actually streamed or polled.
 */
export const LiveDot: React.FC<{ className?: string }> = ({
  className = '',
}) => (
  <span
    aria-hidden="true"
    className={`relative inline-flex h-2 w-2 rounded-full bg-live motion-safe:animate-live-pulse ${className}`}
  />
);

/** A hairline bordered panel on raised paper, the base card of the site. */
export const Panel: React.FC<
  DrawingProps & { as?: 'div' | 'article' | 'section' | 'li' }
> = ({ as: Tag = 'div', className = '', children }) => (
  <Tag className={`relative border border-line bg-paper-raised ${className}`}>
    {children}
  </Tag>
);
