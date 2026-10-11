import React, { useState } from 'react';
import { useInViewReveal } from '../../hooks';
import { getProjects } from '../../content';
import type { Project } from '../../content';
import {
  MonoLabel,
  RegistrationMarks,
  SectionHeading,
  Sheet,
} from '../drawing';

const CATEGORIES: { id: string; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'frontend', label: 'Frontend' },
  { id: 'backend', label: 'Backend' },
  { id: 'automation', label: 'Automation' },
];

const CATEGORY_TECHS: Record<string, string[]> = {
  frontend: [
    'react',
    'typescript',
    'javascript',
    'html',
    'css',
    'tailwind',
    'vite',
    'flutter',
    'dart',
  ],
  backend: [
    'fastapi',
    'postgresql',
    'sqlalchemy',
    'pydantic',
    'firebase',
    'nosql',
    'python',
  ],
  automation: ['web scraping', 'automation', 'data processing', 'bash'],
};

/** True when a project's technologies place it in the filter category. */
const matchesCategory = (project: Project, category: string): boolean => {
  if (category === 'all') return true;
  const techs = project.technologies.map((t) => t.toLowerCase());
  const target = CATEGORY_TECHS[category] ?? [];
  return target.some((c) => techs.some((p) => p.includes(c)));
};

/** One project as a drawing card: figure, title, notes and links. */
const ProjectCard: React.FC<{ project: Project; index: number }> = ({
  project,
  index,
}) => {
  const { ref, isInView } = useInViewReveal<HTMLLIElement>({
    threshold: 0.15,
  });
  const ref_ = `P-${String(index + 1).padStart(2, '0')}`;

  return (
    <li
      ref={ref}
      style={{ animationDelay: `${(index % 6) * 60}ms` }}
      className={`group flex flex-col border-b border-r border-line bg-paper-raised/60 transition-colors hover:bg-paper-raised ${isInView ? 'motion-safe:animate-fade-in-up' : 'motion-safe:opacity-0'}`}
    >
      <article className="flex flex-1 flex-col">
        <div className="relative aspect-16/10 overflow-hidden border-b border-line bg-paper-sunk">
          {project.image ? (
            <img
              src={project.image}
              alt=""
              className="h-full w-full object-cover transition-transform duration-700 motion-safe:group-hover:scale-[1.02]"
              loading="lazy"
            />
          ) : (
            <div
              className="flex h-full w-full items-center justify-center"
              aria-hidden="true"
            >
              <svg
                viewBox="0 0 80 50"
                className="h-16 w-24 text-line-strong"
                fill="none"
                stroke="currentColor"
                strokeWidth="1"
              >
                <rect x="1" y="1" width="78" height="48" />
                <path d="M1 1l78 48M79 1 1 49" />
              </svg>
            </div>
          )}
          <span className="absolute left-0 top-0 border-b border-r border-line bg-paper px-2 py-1 font-mono text-[0.6875rem] text-ink-muted">
            {ref_}
          </span>
          {project.featured && (
            <span className="absolute right-0 top-0 border-b border-l border-line bg-paper px-2 py-1 mono-label text-accent">
              Featured
            </span>
          )}
        </div>

        <div className="flex flex-1 flex-col p-5">
          <h3 className="text-lg font-semibold tracking-tight text-ink">
            {project.title}
          </h3>
          <p className="mt-2 flex-1 text-sm leading-relaxed text-ink-muted">
            {project.description}
          </p>

          {project.technologies.length > 0 && (
            <p className="mt-4 font-mono text-xs leading-relaxed text-ink-muted">
              <span className="sr-only">Built with </span>
              {project.technologies.slice(0, 5).join(' / ')}
              {project.technologies.length > 5 &&
                ` / +${project.technologies.length - 5}`}
            </p>
          )}

          {(project.live_url || project.github_url) && (
            <div className="mt-5 flex gap-5 border-t border-line pt-4 text-sm">
              {project.live_url && (
                <a
                  href={project.live_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ink-link font-medium"
                >
                  Live site
                  <span className="sr-only"> for {project.title}</span>
                  <span aria-hidden="true"> ↗</span>
                </a>
              )}
              {project.github_url && (
                <a
                  href={project.github_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ink-link font-medium"
                >
                  Code
                  <span className="sr-only"> for {project.title}</span>
                  <span aria-hidden="true"> ↗</span>
                </a>
              )}
            </div>
          )}
        </div>
      </article>
    </li>
  );
};

const GRID = 'grid border-l border-t border-line sm:grid-cols-2 lg:grid-cols-3';

/** The projects grid, ordered by the configured sort mode. */
export const Projects: React.FC = () => {
  const projects = getProjects();
  const [filter, setFilter] = useState<string>('all');
  const [showAll, setShowAll] = useState(false);

  const filtered = projects.filter((p) => matchesCategory(p, filter));
  const displayed = showAll ? filtered : filtered.slice(0, 6);

  return (
    <section
      id="projects"
      aria-labelledby="projects-title"
      className="border-b border-line py-20 sm:py-28"
    >
      <Sheet>
        <SectionHeading
          index="04"
          label="Projects"
          id="projects-title"
          title="Things I've built"
          aside={
            <MonoLabel>
              {String(filtered.length).padStart(2, '0')} shown
            </MonoLabel>
          }
        >
          A selection of work across web, infrastructure, and automation.
        </SectionHeading>

        <div
          role="group"
          aria-label="Filter projects"
          className="mb-8 inline-flex flex-wrap border-l border-t border-line"
        >
          {CATEGORIES.map((cat) => {
            const active = filter === cat.id;
            return (
              <button
                key={cat.id}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  setFilter(cat.id);
                  setShowAll(false);
                }}
                className={`border-b border-r border-line px-4 py-2 text-sm transition-colors ${
                  active
                    ? 'bg-ink text-paper'
                    : 'text-ink-muted hover:bg-accent-soft hover:text-ink'
                }`}
              >
                {cat.label}
              </button>
            );
          })}
        </div>

        {filtered.length === 0 && (
          <p className="text-ink-muted">No projects in this category yet.</p>
        )}
        {filtered.length > 0 && (
          <ul className={GRID}>
            {displayed.map((project, idx) => (
              <ProjectCard key={project.id} project={project} index={idx} />
            ))}
          </ul>
        )}

        {filtered.length > 6 && (
          <div className="mt-8">
            <button
              type="button"
              onClick={() => setShowAll((prev) => !prev)}
              className="border border-line-strong px-5 py-2.5 text-sm text-ink transition-colors hover:border-ink"
            >
              {showAll ? 'Show fewer' : `Show ${filtered.length - 6} more`}
            </button>
          </div>
        )}

        <div className="relative mt-20 border border-line bg-paper-raised/70 px-6 py-10 sm:px-10">
          <RegistrationMarks />
          <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div>
              <MonoLabel as="p">Open to work</MonoLabel>
              <h3 className="mt-3 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
                Have something in mind?
              </h3>
              <p className="mt-3 max-w-xl text-ink-muted">
                Always interested in interesting work: backend systems,
                full-stack projects, or anything that needs a careful pair of
                hands.
              </p>
            </div>
            <a
              href="#contact"
              className="inline-flex shrink-0 items-center justify-center gap-2 border border-ink bg-ink px-5 py-3 text-sm font-medium text-paper transition-colors hover:border-accent hover:bg-accent"
            >
              Get in touch <span aria-hidden="true">→</span>
            </a>
          </div>
        </div>
      </Sheet>
    </section>
  );
};
