import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Header, Footer } from '../layout';
import { GradientText } from '../common';
import { apiService } from '../../services/api';
import { useInViewReveal } from '../../hooks';
import type { BlogPost } from '../../services/api';
import type { NavigationItem } from '../../types';

const NAV: NavigationItem[] = [
  { label: 'Home', href: '/' },
  { label: 'About', href: '/#about' },
  { label: 'Skills', href: '/#skills' },
  { label: 'Projects', href: '/#projects' },
  { label: 'Experience', href: '/#experience' },
  { label: 'Blog', href: '/blog' },
  { label: 'Contact', href: '/#contact' },
];

const formatDate = (iso?: string): string =>
  iso
    ? new Date(iso).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : '';

const BlogPostCard: React.FC<{ post: BlogPost; index: number }> = ({
  post,
  index,
}) => {
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({
    threshold: 0.15,
  });
  return (
    <Link
      to={`/blog/${post.slug}`}
      ref={ref as React.Ref<HTMLAnchorElement>}
      style={{ animationDelay: `${(index % 9) * 60}ms` }}
      className={`group surface-glass surface-glass-hover rounded-2xl p-6 flex flex-col h-full transition-all duration-500 hover:-translate-y-1 hover:shadow-glow-soft ${isInView ? 'animate-fade-in-up' : 'opacity-0'}`}
    >
      <div className="flex items-center justify-between mb-4">
        {post.category && (
          <span className="px-2.5 py-0.5 text-xs rounded-full bg-gradient-to-r from-accent-violet-500/20 to-accent-fuchsia-500/20 border border-accent-violet-500/30 text-surface-100">
            {post.category.name}
          </span>
        )}
        {post.read_time && (
          <span className="text-xs text-surface-400 uppercase tracking-[0.16em]">
            {post.read_time}
          </span>
        )}
      </div>
      <h3 className="font-display text-lg font-semibold text-surface-50 mb-2 leading-snug group-hover:text-gradient transition-colors">
        {post.title}
      </h3>
      {post.excerpt && (
        <p className="text-surface-300 text-sm leading-relaxed mb-4 flex-1">
          {post.excerpt}
        </p>
      )}
      <div className="mt-auto flex items-center justify-between text-sm">
        <span className="text-surface-400 text-xs">
          {formatDate(post.published_at)}
        </span>
        <span className="text-accent-cyan-400 text-xs group-hover:translate-x-1 transition-transform">
          Read →
        </span>
      </div>
    </Link>
  );
};

/** The full blog index at its own route. */
export const BlogList: React.FC = () => {
  const [blogPosts, setBlogPosts] = useState<BlogPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [categories, setCategories] = useState<
    { id: number; name: string; slug: string }[]
  >([]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      const [postsResponse, categoriesResponse] = await Promise.all([
        apiService.getBlogPosts(),
        apiService.getCategories(),
      ]);
      if (cancelled) return;
      if (postsResponse.error) setError(postsResponse.error);
      else setBlogPosts(postsResponse.data || []);
      if (!categoriesResponse.error)
        setCategories(categoriesResponse.data || []);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = selectedCategory
    ? blogPosts.filter(p => p.category?.slug === selectedCategory)
    : blogPosts;
  const published = filtered.filter(p => p.published_at);

  return (
    <div className="min-h-screen">
      <Header navigationItems={NAV} />
      <main className="relative py-20 sm:py-28 overflow-hidden">
        <div className="absolute inset-0 bg-mesh-1 opacity-40 pointer-events-none" />
        <div className="relative z-10 max-w-7xl mx-auto px-6 sm:px-8">
          <div className="text-center mb-12 max-w-2xl mx-auto">
            <span className="inline-block text-xs uppercase tracking-[0.2em] text-accent-violet-400 mb-4">
              Writing
            </span>
            <h1 className="font-display text-4xl sm:text-5xl font-bold text-surface-50 mb-4">
              Blog & <GradientText as="span">articles</GradientText>
            </h1>
            <p className="text-surface-300 text-lg">
              Thoughts on engineering, infrastructure, and adjacent topics.
            </p>
          </div>

          {categories.length > 0 && (
            <div className="flex flex-wrap justify-center gap-2 mb-12">
              <button
                type="button"
                onClick={() => setSelectedCategory(null)}
                className={`px-4 py-1.5 text-sm rounded-full transition-all duration-300 ${
                  selectedCategory === null
                    ? 'bg-gradient-accent text-surface-50 shadow-glow-violet'
                    : 'surface-glass text-surface-300 hover:text-surface-50'
                }`}
                style={
                  selectedCategory === null
                    ? { backgroundSize: '200% 200%' }
                    : undefined
                }
              >
                All
              </button>
              {categories.map(c => {
                const active = selectedCategory === c.slug;
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setSelectedCategory(c.slug)}
                    className={`px-4 py-1.5 text-sm rounded-full transition-all duration-300 ${
                      active
                        ? 'bg-gradient-accent text-surface-50 shadow-glow-violet'
                        : 'surface-glass text-surface-300 hover:text-surface-50'
                    }`}
                    style={active ? { backgroundSize: '200% 200%' } : undefined}
                  >
                    {c.name}
                  </button>
                );
              })}
            </div>
          )}

          {loading && (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <div
                  key={i}
                  className="h-48 surface-glass rounded-2xl animate-pulse"
                />
              ))}
            </div>
          )}
          {error && !loading && (
            <p className="text-center text-surface-400">
              Couldn't load posts right now.
            </p>
          )}
          {!loading && !error && published.length === 0 && (
            <p className="text-center text-surface-400">
              {selectedCategory
                ? 'No posts in this category yet.'
                : 'No posts yet — check back soon.'}
            </p>
          )}
          {!loading && !error && published.length > 0 && (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {published.map((post, i) => (
                <BlogPostCard key={post.id} post={post} index={i} />
              ))}
            </div>
          )}

          <div className="text-center mt-16">
            <Link
              to="/"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-full surface-glass surface-glass-hover text-surface-100"
            >
              ← Back to home
            </Link>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
};
