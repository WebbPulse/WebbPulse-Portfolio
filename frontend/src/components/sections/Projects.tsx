import React, { useState } from 'react';
import { GradientText, GradientPanel } from '../common';
import { useProjects, useInViewReveal } from '../../hooks';
import type { Project } from '../../services/api';

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

const matchesCategory = (project: Project, category: string): boolean => {
  if (category === 'all') return true;
  const techs = project.technologies.map((t) => t.toLowerCase());
  const target = CATEGORY_TECHS[category] ?? [];
  return target.some((c) => techs.some((p) => p.includes(c)));
};

const ProjectCard: React.FC<{ project: Project; index: number }> = ({
  project,
  index,
}) => {
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({
    threshold: 0.15,
  });

  return (
    <article
      ref={ref}
      style={{ animationDelay: `${(index % 6) * 70}ms` }}
      className={`group gradient-border relative rounded-2xl bg-surface-900/70 backdrop-blur-xl overflow-hidden flex flex-col transition-all duration-500 hover:-translate-y-1 hover:shadow-glow-soft ${isInView ? 'animate-fade-in-up' : 'opacity-0'}`}
    >
      <div className="relative aspect-[16/10] overflow-hidden bg-gradient-to-br from-accent-violet-500/20 via-accent-cyan-500/10 to-accent-fuchsia-500/20">
        {project.image ? (
          <img
            src={project.image}
            alt={project.title}
            className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-5xl opacity-50">
            ✨
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-surface-950 via-surface-950/40 to-transparent" />
        {project.featured && (
          <span className="absolute top-3 right-3 px-2.5 py-1 text-[10px] uppercase tracking-[0.16em] font-medium rounded-full bg-gradient-accent text-surface-50 shadow-glow-violet">
            Featured
          </span>
        )}
      </div>

      <div className="relative flex-1 p-6 flex flex-col">
        <h3 className="font-display text-xl font-semibold text-surface-50 mb-2 group-hover:text-gradient transition-colors">
          {project.title}
        </h3>
        <p className="text-surface-300 text-sm leading-relaxed mb-4 flex-1">
          {project.description}
        </p>

        <div className="flex flex-wrap gap-1.5 mb-5">
          {project.technologies.slice(0, 4).map((tech) => (
            <span
              key={tech}
              className="px-2.5 py-0.5 text-xs rounded-full bg-surface-800 border border-surface-700 text-surface-200"
            >
              {tech}
            </span>
          ))}
          {project.technologies.length > 4 && (
            <span className="px-2.5 py-0.5 text-xs rounded-full bg-surface-800/50 border border-surface-700/50 text-surface-400">
              +{project.technologies.length - 4}
            </span>
          )}
        </div>

        <div className="flex gap-3 mt-auto">
          {project.live_url && (
            <a
              href={project.live_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-full bg-gradient-accent text-surface-50 shadow-glow-violet/40 hover:shadow-glow-fuchsia transition-shadow"
              style={{ backgroundSize: '200% 200%' }}
            >
              Live →
            </a>
          )}
          {project.github_url && (
            <a
              href={project.github_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 inline-flex items-center justify-center px-4 py-2 text-sm font-medium rounded-full surface-glass surface-glass-hover text-surface-100"
            >
              Code
            </a>
          )}
        </div>
      </div>
    </article>
  );
};

const SkeletonCard: React.FC = () => (
  <div className="surface-glass rounded-2xl overflow-hidden animate-pulse">
    <div className="aspect-[16/10] bg-surface-800" />
    <div className="p-6 space-y-3">
      <div className="h-5 bg-surface-800 rounded w-2/3" />
      <div className="h-3 bg-surface-800 rounded" />
      <div className="h-3 bg-surface-800 rounded w-5/6" />
    </div>
  </div>
);

/** The projects grid, ordered by the configured sort mode. */
export const Projects: React.FC = () => {
  const { data, loading, error } = useProjects();
  const [filter, setFilter] = useState<string>('all');
  const [showAll, setShowAll] = useState(false);

  const projects = data ?? [];
  const filtered = projects.filter((p) => matchesCategory(p, filter));
  const displayed = showAll ? filtered : filtered.slice(0, 6);

  return (
    <section
      id="projects"
      className="relative py-24 sm:py-32 overflow-hidden bg-surface-950"
    >
      <div className="absolute inset-0 bg-gradient-to-b from-surface-950 via-surface-900/60 to-surface-950 pointer-events-none" />

      <div className="relative z-10 max-w-7xl mx-auto px-6 sm:px-8">
        <div className="text-center mb-12 max-w-2xl mx-auto">
          <span className="inline-block text-xs uppercase tracking-[0.2em] text-accent-cyan-400 mb-4">
            Projects
          </span>
          <h2 className="font-display text-4xl sm:text-5xl font-bold text-surface-50 mb-4">
            Things I've <GradientText as="span">built</GradientText>
          </h2>
          <p className="text-surface-300 text-lg">
            A selection of work across web, infrastructure, and automation.
          </p>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap justify-center gap-2 mb-12">
          {CATEGORIES.map((cat) => {
            const active = filter === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => {
                  setFilter(cat.id);
                  setShowAll(false);
                }}
                className={`px-4 py-1.5 text-sm rounded-full transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-950 ${
                  active
                    ? 'bg-gradient-accent text-surface-50 shadow-glow-violet'
                    : 'surface-glass text-surface-300 hover:text-surface-50'
                }`}
                style={active ? { backgroundSize: '200% 200%' } : undefined}
              >
                {cat.label}
              </button>
            );
          })}
        </div>

        {/* Grid */}
        {loading && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}
        {error && !loading && (
          <p className="text-center text-surface-400">
            Couldn't load projects right now.
          </p>
        )}
        {!loading && !error && filtered.length === 0 && (
          <p className="text-center text-surface-400">
            No projects in this category yet.
          </p>
        )}
        {!loading && !error && filtered.length > 0 && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {displayed.map((project, idx) => (
              <ProjectCard key={project.id} project={project} index={idx} />
            ))}
          </div>
        )}

        {filtered.length > 6 && (
          <div className="text-center mt-10">
            <button
              type="button"
              onClick={() => setShowAll((prev) => !prev)}
              className="px-6 py-2 rounded-full surface-glass surface-glass-hover text-surface-100 text-sm"
            >
              {showAll ? 'Show fewer' : `Show ${filtered.length - 6} more`}
            </button>
          </div>
        )}

        <div className="mt-20">
          <GradientPanel className="px-8 py-12 text-center">
            <h3 className="font-display text-2xl sm:text-3xl font-bold text-surface-50 mb-3">
              Have something in mind?
            </h3>
            <p className="text-surface-300 max-w-xl mx-auto mb-6">
              Always interested in interesting work — backend systems,
              full-stack projects, or anything that needs a careful pair of
              hands.
            </p>
            <a
              href="#contact"
              onClick={(e) => {
                e.preventDefault();
                document
                  .querySelector('#contact')
                  ?.scrollIntoView({ behavior: 'smooth' });
              }}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-gradient-accent text-surface-50 shadow-glow-violet hover:shadow-glow-fuchsia transition-shadow"
              style={{ backgroundSize: '200% 200%' }}
            >
              Get in touch <span>→</span>
            </a>
          </GradientPanel>
        </div>
      </div>
    </section>
  );
};
