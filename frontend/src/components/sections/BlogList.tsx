import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { PublicShell } from '../layout';
import { getCategories, getPublishedPosts } from '../../content';
import { useDocumentMeta } from '../../hooks';
import { MonoLabel, Sheet } from '../drawing';
import { PostRow } from './PostRow';

/** A category filter chip. */
const FilterChip: React.FC<{
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}> = ({ active, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    aria-pressed={active}
    className={`border px-3 py-1.5 font-mono text-xs uppercase tracking-[0.08em] transition-colors ${
      active
        ? 'border-ink bg-ink text-paper'
        : 'border-line text-ink-muted hover:border-line-strong hover:text-ink'
    }`}
  >
    {children}
  </button>
);

/** The full blog index at its own route. */
export const BlogList: React.FC = () => {
  useDocumentMeta({
    title: 'Writing',
    description: 'Posts by Tyler Webb on the systems he builds and runs.',
  });
  const blogPosts = getPublishedPosts();
  const categories = getCategories();
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const published = selectedCategory
    ? blogPosts.filter((p) => p.category?.slug === selectedCategory)
    : blogPosts;

  return (
    <PublicShell>
      <main id="main" className="flex-1" data-testid="page-blog-list">
        <Sheet className="py-16 sm:py-24">
          <div className="border-b border-line pb-10">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-accent">B</span>
              <span className="h-3 w-px bg-line-strong" aria-hidden="true" />
              <MonoLabel>Writing</MonoLabel>
            </div>
            <h1 className="mt-5 text-4xl font-semibold tracking-[-0.02em] text-ink sm:text-5xl">
              Notes and articles
            </h1>
            <p className="mt-4 max-w-2xl text-lg leading-relaxed text-ink-muted">
              Thoughts on engineering, infrastructure, and adjacent topics.
            </p>
          </div>

          {categories.length > 0 && (
            <div
              role="group"
              aria-label="Filter by category"
              className="flex flex-wrap gap-2 py-6"
            >
              <FilterChip
                active={selectedCategory === null}
                onClick={() => setSelectedCategory(null)}
              >
                All
              </FilterChip>
              {categories.map((c) => (
                <FilterChip
                  key={c.id}
                  active={selectedCategory === c.slug}
                  onClick={() => setSelectedCategory(c.slug)}
                >
                  {c.name}
                </FilterChip>
              ))}
            </div>
          )}

          {published.length === 0 && (
            <p className="py-6 text-ink-muted">
              {selectedCategory
                ? 'No posts in this category yet.'
                : 'No posts yet. Check back soon.'}
            </p>
          )}
          {published.length > 0 && (
            <ul className="border-t border-line-strong">
              {published.map((post) => (
                <PostRow key={post.id} post={post} headingLevel="h2" />
              ))}
            </ul>
          )}

          <div className="mt-12">
            <Link to="/" className="ink-link text-sm">
              <span aria-hidden="true">← </span>Back to home
            </Link>
          </div>
        </Sheet>
      </main>
    </PublicShell>
  );
};
