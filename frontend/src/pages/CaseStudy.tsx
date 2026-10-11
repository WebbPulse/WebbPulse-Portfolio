import React, { useLayoutEffect, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { PublicShell } from '../components/layout';
import { MonoLabel, Sheet } from '../components/drawing';
import { getCaseStudy, getProjectBySlug } from '../content';
import {
  listCaseStudies,
  manName,
  resolveCaseStudy,
  type CaseStudyView,
} from '../content/caseStudies';
import { loadCaseStudies } from '../content/loaders';
import { useDocumentMeta } from '../hooks';
import { extractHeadings, processMarkdown } from '../utils/markdown';

/** Every case study, for the see also list. */
const ALL_CASE_STUDIES = listCaseStudies(loadCaseStudies());

/** One man page section: a mono name in the gutter and its content. */
const Section: React.FC<{
  name: string;
  id?: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
}> = ({ name, id, aside, children }) => (
  <section
    aria-labelledby={id}
    className="grid grid-cols-1 gap-3 border-t border-line py-8 lg:grid-cols-[11rem_minmax(0,1fr)] lg:gap-10"
  >
    <div>
      <h2 id={id} className="mono-label text-ink">
        {name}
      </h2>
      {aside}
    </div>
    <div className="min-w-0">{children}</div>
  </section>
);

/** The running header and footer line of a man page. */
const ManLine: React.FC<{ left: string; centre: string; right: string }> = ({
  left,
  centre,
  right,
}) => (
  <div
    className="flex items-center justify-between gap-4 font-mono text-[0.6875rem] uppercase tracking-[0.08em] text-ink-muted"
    aria-hidden="true"
  >
    <span>{left}</span>
    <span className="hidden sm:inline">{centre}</span>
    <span>{right}</span>
  </div>
);

/** The page for a slug that has neither a case study nor a project. */
const MissingCaseStudy: React.FC = () => (
  <Sheet className="py-20 sm:py-28">
    <MonoLabel as="p">No entry</MonoLabel>
    <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink">
      Case study not found
    </h1>
    <p className="mt-4 max-w-xl text-ink-muted">
      There is no write-up at this address. The system map on the home page
      links to every one that exists.
    </p>
    <Link to="/" className="ink-link mt-8 inline-block text-sm">
      <span aria-hidden="true">← </span>Back to the map
    </Link>
  </Sheet>
);

/** The man page body for one resolved case study. */
const CaseStudyBody: React.FC<{ view: CaseStudyView }> = ({ view }) => {
  const name = manName(view.slug);
  const headings = useMemo(
    () =>
      view.hasWriteUp
        ? extractHeadings(view.body).filter((h) => h.level === 2)
        : [],
    [view.hasWriteUp, view.body]
  );
  const html = useMemo(
    () => (view.hasWriteUp ? processMarkdown(view.body, { styled: false }) : ''),
    [view.hasWriteUp, view.body]
  );
  const others = useMemo(
    () => ALL_CASE_STUDIES.filter((entry) => entry.slug !== view.slug),
    [view.slug]
  );
  const backState = view.mapNodeId ? { focusNode: view.mapNodeId } : null;

  return (
    <Sheet className="py-10 sm:py-14">
      <ManLine
        left={`${name}(7)`}
        centre="WebbPulse case studies"
        right={`${name}(7)`}
      />

      <header
        data-case-study-head=""
        className="case-study-head mt-8 border border-line bg-paper-raised px-5 py-6 sm:px-8 sm:py-8"
      >
        <Link to="/" state={backState} className="ink-link text-sm">
          <span aria-hidden="true">← </span>System map
        </Link>
        <h1 className="mt-5 text-4xl font-semibold leading-[1.08] tracking-[-0.02em] text-ink md:text-5xl">
          {view.title}
        </h1>
        {view.summary && (
          <p className="mt-4 max-w-3xl text-lg leading-relaxed text-ink-muted">
            {view.summary}
          </p>
        )}
      </header>

      <div className="mt-10">
        <Section name="Name" id="cs-name">
          <p className="font-mono text-sm text-ink">
            {view.slug}
            <span className="text-ink-faint"> - </span>
            <span className="font-sans text-ink-muted">{view.title}</span>
          </p>
        </Section>

        <Section name="Synopsis" id="cs-synopsis">
          <dl className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-[8rem_minmax(0,1fr)]">
            {view.role && (
              <>
                <dt className="mono-label pt-0.5">Role</dt>
                <dd className="text-sm text-ink">{view.role}</dd>
              </>
            )}
            {view.period && (
              <>
                <dt className="mono-label pt-0.5">Period</dt>
                <dd className="text-sm text-ink">{view.period}</dd>
              </>
            )}
            {view.stack.length > 0 && (
              <>
                <dt className="mono-label pt-0.5">Stack</dt>
                <dd>
                  <ul className="flex flex-wrap gap-1.5" aria-label="Stack">
                    {view.stack.map((item) => (
                      <li
                        key={item}
                        className="border border-line px-1.5 py-0.5 font-mono text-[0.6875rem] text-ink-muted"
                      >
                        {item}
                      </li>
                    ))}
                  </ul>
                </dd>
              </>
            )}
          </dl>
        </Section>

        {view.facts.length > 0 && (
          <Section name="Figures" id="cs-figures">
            <dl className="grid grid-cols-1 border-l border-t border-line sm:grid-cols-2">
              {view.facts.map((fact) => (
                <div
                  key={fact.label}
                  className="border-b border-r border-line px-3 py-2.5"
                >
                  <dt className="mono-label">{fact.label}</dt>
                  <dd className="mt-1 text-sm text-ink">{fact.value}</dd>
                </div>
              ))}
            </dl>
          </Section>
        )}

        <Section
          name="Description"
          id="cs-description"
          aside={
            headings.length > 0 ? (
              <nav aria-label="Sections" className="mt-4 hidden lg:block">
                <ul className="space-y-1.5 border-l border-line">
                  {headings.map((heading) => (
                    <li key={heading.id}>
                      <a
                        href={`#${heading.id}`}
                        className="-ml-px block border-l border-transparent pl-3 text-xs text-ink-muted transition-colors hover:border-accent hover:text-ink"
                      >
                        {heading.text}
                      </a>
                    </li>
                  ))}
                </ul>
              </nav>
            ) : null
          }
        >
          {view.hasWriteUp ? (
            <div
              className="prose case-study-prose max-w-none"
              dangerouslySetInnerHTML={{ __html: html }}
            />
          ) : (
            <div className="max-w-3xl space-y-4 text-ink-muted">
              <p className="leading-relaxed">{view.body}</p>
              <p className="mono-label">Full write-up in progress.</p>
            </div>
          )}
        </Section>

        <Section name="See also" id="cs-see-also">
          <ul className="space-y-2 text-sm">
            {view.links.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ink-link"
                >
                  {link.label}
                </a>
              </li>
            ))}
            {others.map((entry) => (
              <li key={entry.slug}>
                <Link to={`/work/${entry.slug}`} className="ink-link">
                  {manName(entry.slug).toLowerCase()}(7)
                </Link>
                <span className="text-ink-muted"> {entry.title}</span>
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <div className="border-t border-line pt-3">
        <ManLine
          left="WebbPulse"
          centre={view.period || 'Case study'}
          right={`${name}(7)`}
        />
      </div>
    </Sheet>
  );
};

/**
 * A case study as a man page, resolved from the slug in the route.
 *
 * The case study file supplies the write-up and the project entry fills any
 * gaps, so either one alone renders a page.
 */
export const CaseStudy: React.FC = () => {
  const { slug = '' } = useParams<{ slug: string }>();
  const view = resolveCaseStudy(
    slug,
    getCaseStudy(slug),
    getProjectBySlug(slug)
  );

  useDocumentMeta({
    title: view ? view.title : 'Case study not found',
    description: view?.summary || undefined,
  });

  useLayoutEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [slug]);

  return (
    <PublicShell>
      <main id="main" className="flex-1" data-testid="page-case-study">
        {view ? <CaseStudyBody view={view} /> : <MissingCaseStudy />}
      </main>
    </PublicShell>
  );
};

export default CaseStudy;
