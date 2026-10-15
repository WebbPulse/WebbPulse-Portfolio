import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { PublicShell } from '../layout';
import { getPostBySlug, getSiteContent } from '../../content';
import { useClientValue, useDocumentMeta } from '../../hooks';
import { processMarkdown, extractHeadings } from '../../utils/markdown';
import { MonoLabel, Sheet } from '../drawing';

/** A date in long form. */
const longDate = (iso: string): string =>
  new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  });

/** True when the browser offers the native share sheet. */
const browserCanShare = (): boolean =>
  typeof navigator !== 'undefined' && 'share' in navigator;

/** A centred message in place of a post that does not exist. */
const Placeholder: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <PublicShell>
    <main
      id="main"
      className="flex flex-1 items-center justify-center px-4 py-24"
      data-testid="page-blog-post"
    >
      <div className="max-w-md text-center">{children}</div>
    </main>
  </PublicShell>
);

/** Share and copy link controls for the current page. */
const ShareControls: React.FC<{ title: string }> = ({ title }) => {
  const [copied, setCopied] = useState(false);
  const canShare = useClientValue(browserCanShare, false);

  return (
    <div className="flex gap-2">
      {canShare && (
        <button
          type="button"
          onClick={() => {
            void navigator
              .share({ title, url: window.location.href })
              .catch(() => {});
          }}
          className="flex-1 border border-line-strong px-3 py-2 text-sm text-ink transition-colors hover:border-ink"
        >
          Share
        </button>
      )}
      <button
        type="button"
        onClick={() => {
          void navigator.clipboard
            ?.writeText(window.location.href)
            .then(() => setCopied(true))
            .catch(() => {});
        }}
        className="flex-1 border border-line-strong px-3 py-2 text-sm text-ink transition-colors hover:border-ink"
      >
        <span aria-live="polite">{copied ? 'Copied' : 'Copy link'}</span>
      </button>
    </div>
  );
};

/** One blog post, resolved from the slug in the route. */
export const BlogPost: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const post = slug ? getPostBySlug(slug) : undefined;
  const [readingProgress, setReadingProgress] = useState(0);
  const [showToc, setShowToc] = useState(false);
  const site = getSiteContent();
  useDocumentMeta({
    title: post ? post.title : 'Post not found',
    description: post?.excerpt || undefined,
    noindex: !post,
  });

  useEffect(() => {
    const onScroll = () => {
      const docHeight =
        document.documentElement.scrollHeight - window.innerHeight;
      setReadingProgress(
        docHeight > 0 ? Math.min((window.scrollY / docHeight) * 100, 100) : 0
      );
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  if (!post) {
    return (
      <Placeholder>
        <MonoLabel as="p">Not found</MonoLabel>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink">
          Post not found
        </h1>
        <p className="mt-4 text-ink-muted">
          The post you&apos;re looking for doesn&apos;t exist or hasn&apos;t
          been published yet.
        </p>
        <Link to="/blog" className="ink-link mt-8 inline-block text-sm">
          <span aria-hidden="true">← </span>Back to blog
        </Link>
      </Placeholder>
    );
  }

  const headings = extractHeadings(post.content);
  const processed = processMarkdown(post.content, { styled: false });
  const profileImage = site.profile_image_url ?? '/headshot.jpg';

  return (
    <PublicShell>
      <div
        className="fixed inset-x-0 top-0 z-[60] h-0.5 bg-transparent"
        aria-hidden="true"
      >
        <div
          className="h-full origin-left bg-accent"
          style={{ transform: `scaleX(${readingProgress / 100})` }}
        />
      </div>

      <main id="main" className="flex-1" data-testid="page-blog-post">
        <Sheet className="py-14 sm:py-20">
          <div className="grid grid-cols-1 gap-12 lg:grid-cols-12">
            <article className="min-w-0 lg:col-span-8">
              <header className="border-b border-line pb-8">
                <Link to="/blog" className="ink-link text-sm">
                  <span aria-hidden="true">← </span>All posts
                </Link>
                <div className="mt-8 flex flex-wrap items-center gap-3">
                  {post.category && (
                    <MonoLabel className="text-accent">
                      {post.category.name}
                    </MonoLabel>
                  )}
                  {post.category && post.read_time && (
                    <span
                      className="h-3 w-px bg-line-strong"
                      aria-hidden="true"
                    />
                  )}
                  {post.read_time && <MonoLabel>{post.read_time}</MonoLabel>}
                </div>

                <h1 className="mt-4 text-4xl font-semibold leading-[1.08] tracking-[-0.02em] text-ink md:text-5xl">
                  {post.title}
                </h1>

                {post.excerpt && (
                  <p className="mt-5 text-xl leading-relaxed text-ink-muted">
                    {post.excerpt}
                  </p>
                )}

                <div className="mt-8 flex items-center gap-3 text-sm">
                  <img
                    src={profileImage}
                    alt=""
                    className="h-9 w-9 border border-line object-cover"
                  />
                  <span className="text-ink">Tyler Webb</span>
                  {post.published_at && (
                    <>
                      <span className="text-ink-faint" aria-hidden="true">
                        /
                      </span>
                      <time
                        dateTime={post.published_at}
                        className="font-mono text-xs text-ink-muted"
                      >
                        {longDate(post.published_at)}
                      </time>
                    </>
                  )}
                </div>
              </header>

              <div
                className="prose prose-lg mt-10 max-w-none"
                dangerouslySetInnerHTML={{ __html: processed }}
              />

              <footer className="mt-16 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-8">
                <div className="text-sm text-ink-muted">
                  <p>Written by Tyler Webb</p>
                  {post.updated_at && post.updated_at !== post.created_at && (
                    <p className="mt-1 font-mono text-xs">
                      Last updated {longDate(post.updated_at)}
                    </p>
                  )}
                </div>
                <Link to="/blog" className="ink-link text-sm">
                  All posts <span aria-hidden="true">→</span>
                </Link>
              </footer>
            </article>

            <aside className="lg:col-span-4" aria-label="Post tools">
              <div className="space-y-6 lg:sticky lg:top-24">
                {headings.length > 0 && (
                  <nav
                    aria-label="On this page"
                    className="border border-line bg-paper-raised/70 p-5"
                  >
                    <div className="flex items-center justify-between">
                      <MonoLabel as="h2">On this page</MonoLabel>
                      <button
                        type="button"
                        onClick={() => setShowToc((prev) => !prev)}
                        className="text-ink-muted hover:text-ink lg:hidden"
                        aria-label="Toggle table of contents"
                        aria-expanded={showToc}
                        aria-controls="post-toc"
                      >
                        <svg
                          className={`h-4 w-4 transition-transform ${showToc ? 'rotate-180' : ''}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 16 16"
                          strokeWidth={1.5}
                          aria-hidden="true"
                        >
                          <path d="m4 6 4 4 4-4" />
                        </svg>
                      </button>
                    </div>
                    <ul
                      id="post-toc"
                      className={`mt-3 space-y-1.5 border-l border-line ${showToc ? 'block' : 'hidden lg:block'}`}
                    >
                      {headings.map((h, i) => (
                        <li key={i}>
                          <a
                            href={`#${h.id}`}
                            className={`-ml-px block border-l border-transparent py-0.5 text-sm transition-colors hover:border-accent hover:text-accent ${
                              h.level === 2
                                ? 'pl-3 text-ink'
                                : 'pl-6 text-ink-muted'
                            }`}
                          >
                            {h.text}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </nav>
                )}

                <div className="border border-line bg-paper-raised/70 p-5">
                  <MonoLabel as="h2" className="mb-3 block">
                    Share
                  </MonoLabel>
                  <ShareControls title={post.title} />
                </div>
              </div>
            </aside>
          </div>
        </Sheet>
      </main>
    </PublicShell>
  );
};
