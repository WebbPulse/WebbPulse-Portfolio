import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Header, Footer } from '../layout';
import { apiService } from '../../services/api';
import { useSiteContent } from '../../hooks';
import type { BlogPost as BlogPostType } from '../../services/api';
import type { NavigationItem } from '../../types';
import { processMarkdown, extractHeadings } from '../../utils/markdown';

const NAV: NavigationItem[] = [
  { label: 'Home', href: '/' },
  { label: 'About', href: '/#about' },
  { label: 'Skills', href: '/#skills' },
  { label: 'Projects', href: '/#projects' },
  { label: 'Experience', href: '/#experience' },
  { label: 'Blog', href: '/blog' },
  { label: 'Contact', href: '/#contact' },
];

export const BlogPost: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const [post, setPost] = useState<BlogPostType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [readingProgress, setReadingProgress] = useState(0);
  const [showToc, setShowToc] = useState(false);
  const { data: site } = useSiteContent();

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      const response = await apiService.getBlogPostBySlug(slug);
      if (cancelled) return;
      if (response.error) setError(response.error);
      else setPost(response.data);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  useEffect(() => {
    const onScroll = () => {
      const top = window.scrollY;
      const docHeight =
        document.documentElement.scrollHeight - window.innerHeight;
      setReadingProgress(Math.min((top / docHeight) * 100, 100));
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header navigationItems={NAV} />
        <main className="flex items-center justify-center min-h-[60vh]">
          <div className="text-center">
            <div className="animate-spin rounded-full h-10 w-10 border-2 border-accent-violet-500 border-t-transparent mx-auto mb-4" />
            <p className="text-surface-300">Loading…</p>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  if (error || !post) {
    return (
      <div className="min-h-screen">
        <Header navigationItems={NAV} />
        <main className="flex items-center justify-center min-h-[60vh]">
          <div className="text-center max-w-md mx-auto px-6">
            <h1 className="font-display text-2xl font-bold text-surface-50 mb-4">
              Post not found
            </h1>
            <p className="text-surface-300 mb-6">
              {error ||
                "The post you're looking for doesn't exist (or hasn't been published yet)."}
            </p>
            <Link
              to="/blog"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-gradient-accent text-surface-50 shadow-glow-violet"
              style={{ backgroundSize: '200% 200%' }}
            >
              ← Back to blog
            </Link>
          </div>
        </main>
        <Footer />
      </div>
    );
  }

  const headings = extractHeadings(post.content);
  const processed = processMarkdown(post.content);
  const profileImage = site?.profile_image_url ?? '/headshot.jpg';

  return (
    <div className="min-h-screen">
      {/* Reading progress */}
      <div
        className="fixed top-0 left-0 right-0 h-1 bg-surface-900/80 z-50"
        aria-hidden="true"
      >
        <div
          className="h-full bg-gradient-accent transition-all duration-150 ease-out"
          style={{ width: `${readingProgress}%`, backgroundSize: '200% 200%' }}
        />
      </div>

      <Header navigationItems={NAV} />
      <main className="relative py-20 sm:py-28 overflow-hidden">
        <div className="absolute inset-0 bg-mesh-1 opacity-30 pointer-events-none" />
        <div className="relative z-10 max-w-6xl mx-auto px-6 sm:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-10">
            <article className="lg:col-span-3">
              <header className="mb-10">
                <div className="flex flex-wrap items-center gap-3 mb-6">
                  {post.category && (
                    <span
                      className="px-3 py-1 text-xs rounded-full bg-gradient-accent text-surface-50 font-medium"
                      style={{ backgroundSize: '200% 200%' }}
                    >
                      {post.category.name}
                    </span>
                  )}
                  {post.read_time && (
                    <span className="text-xs text-surface-400 uppercase tracking-[0.16em]">
                      {post.read_time}
                    </span>
                  )}
                </div>

                <h1 className="font-display text-4xl md:text-5xl lg:text-6xl font-bold text-surface-50 mb-6 leading-[1.1]">
                  {post.title}
                </h1>

                {post.excerpt && (
                  <p className="text-xl text-surface-300 mb-8 leading-relaxed">
                    {post.excerpt}
                  </p>
                )}

                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 text-sm text-surface-400 border-t border-surface-800 pt-6">
                  <div className="flex items-center gap-3">
                    <img
                      src={profileImage}
                      alt="Tyler Webb"
                      className="w-9 h-9 rounded-full object-cover ring-2 ring-accent-violet-500/40"
                    />
                    <span className="text-surface-200">Tyler Webb</span>
                    <span className="text-surface-600">·</span>
                    <span>
                      {post.published_at &&
                        new Date(post.published_at).toLocaleDateString(
                          'en-US',
                          {
                            year: 'numeric',
                            month: 'long',
                            day: 'numeric',
                          }
                        )}
                    </span>
                  </div>
                  <Link
                    to="/blog"
                    className="inline-flex items-center px-4 py-1.5 text-xs rounded-full surface-glass surface-glass-hover text-surface-200"
                  >
                    ← Back to blog
                  </Link>
                </div>
              </header>

              <div className="prose prose-lg max-w-none">
                <div
                  className="text-surface-200 leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: processed }}
                />
              </div>

              <footer className="mt-16 pt-8 border-t border-surface-800 flex items-center justify-between">
                <div className="text-sm text-surface-400">
                  <p>Written by Tyler Webb</p>
                  {post.updated_at && post.updated_at !== post.created_at && (
                    <p className="text-xs mt-1">
                      Last updated:{' '}
                      {new Date(post.updated_at).toLocaleDateString()}
                    </p>
                  )}
                </div>
                <Link
                  to="/blog"
                  className="inline-flex items-center px-5 py-2 text-sm rounded-full surface-glass surface-glass-hover text-surface-200"
                >
                  All posts →
                </Link>
              </footer>
            </article>

            <aside className="lg:col-span-1">
              <div className="sticky top-24 space-y-5">
                {headings.length > 0 && (
                  <div className="surface-glass rounded-2xl p-5">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-xs uppercase tracking-[0.2em] text-accent-cyan-400 font-medium">
                        On this page
                      </h3>
                      <button
                        type="button"
                        onClick={() => setShowToc(prev => !prev)}
                        className="lg:hidden text-surface-400 hover:text-surface-100"
                        aria-label="Toggle table of contents"
                      >
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          strokeWidth={2}
                          aria-hidden="true"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M19 9l-7 7-7-7"
                          />
                        </svg>
                      </button>
                    </div>
                    <nav className={showToc ? 'block' : 'hidden lg:block'}>
                      <ul className="space-y-1.5">
                        {headings.map((h, i) => (
                          <li key={i}>
                            <a
                              href={`#${h.id}`}
                              className={`block text-sm transition-colors hover:text-accent-cyan-400 ${
                                h.level === 2
                                  ? 'text-surface-200 font-medium'
                                  : 'text-surface-400 ml-3'
                              }`}
                            >
                              {h.text}
                            </a>
                          </li>
                        ))}
                      </ul>
                    </nav>
                  </div>
                )}

                <div className="surface-glass rounded-2xl p-5">
                  <h3 className="text-xs uppercase tracking-[0.2em] text-accent-violet-400 font-medium mb-3">
                    Share
                  </h3>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        // Rejects when the visitor dismisses the share sheet,
                        // which is a normal outcome rather than a failure, so
                        // it is swallowed rather than surfaced.
                        void navigator
                          .share?.({
                            title: post.title,
                            url: window.location.href,
                          })
                          .catch(() => {});
                      }}
                      className="flex-1 px-3 py-2 text-sm rounded-lg bg-gradient-accent text-surface-50"
                      style={{ backgroundSize: '200% 200%' }}
                    >
                      Share
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        // Rejects when the document is not focused or the
                        // permission is denied; neither is worth interrupting
                        // the reader over.
                        void navigator.clipboard
                          .writeText(window.location.href)
                          .catch(() => {});
                      }}
                      className="flex-1 px-3 py-2 text-sm rounded-lg surface-glass surface-glass-hover text-surface-200"
                    >
                      Copy
                    </button>
                  </div>
                </div>
              </div>
            </aside>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
};
