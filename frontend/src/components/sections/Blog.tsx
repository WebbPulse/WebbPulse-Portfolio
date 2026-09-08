import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { GradientText, AnimatedOrb } from '../common';
import { apiService } from '../../services/api';
import { useInViewReveal } from '../../hooks';
import type { BlogPost } from '../../services/api';

const formatDate = (iso?: string): string =>
  iso
    ? new Date(iso).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : '';

const FeaturedCard: React.FC<{ post: BlogPost }> = ({ post }) => {
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({ threshold: 0.1 });
  return (
    <Link
      to={`/blog/${post.slug}`}
      ref={ref as React.Ref<HTMLAnchorElement>}
      className={`gradient-border group relative grid md:grid-cols-2 rounded-3xl bg-surface-900/70 backdrop-blur-xl overflow-hidden hover:shadow-glow-soft transition-shadow duration-500 ${isInView ? 'animate-fade-in-up' : 'opacity-0'}`}
    >
      {/* Visual */}
      <div className="relative aspect-[4/3] md:aspect-auto md:min-h-[20rem] overflow-hidden">
        <div className="absolute inset-0 bg-mesh-1" />
        <AnimatedOrb
          gradient="from-accent-cyan-500 to-accent-violet-500"
          size="w-72 h-72"
          position="-top-12 -left-12"
          variant={1}
          opacity="opacity-50"
        />
        <AnimatedOrb
          gradient="from-accent-fuchsia-500 to-accent-violet-500"
          size="w-64 h-64"
          position="bottom-0 right-0"
          variant={2}
          opacity="opacity-40"
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-6xl">📝</span>
        </div>
      </div>
      {/* Content */}
      <div className="p-8 sm:p-10 flex flex-col">
        <div className="flex items-center gap-3 mb-4">
          {post.category && (
            <span className="px-2.5 py-0.5 text-xs rounded-full bg-gradient-to-r from-accent-violet-500/30 to-accent-fuchsia-500/30 border border-accent-violet-500/40 text-surface-100">
              {post.category.name}
            </span>
          )}
          {post.read_time && (
            <span className="text-xs text-surface-400 uppercase tracking-[0.16em]">
              {post.read_time}
            </span>
          )}
        </div>
        <h4 className="font-display text-2xl sm:text-3xl font-bold text-surface-50 mb-3 leading-tight group-hover:text-gradient transition-colors">
          {post.title}
        </h4>
        {post.excerpt && (
          <p className="text-surface-300 leading-relaxed mb-6">
            {post.excerpt}
          </p>
        )}
        <div className="mt-auto flex items-center justify-between text-sm">
          <span className="text-surface-400">
            {formatDate(post.published_at)}
          </span>
          <span className="text-accent-cyan-400 group-hover:translate-x-1 transition-transform">
            Read →
          </span>
        </div>
      </div>
    </Link>
  );
};

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
      style={{ animationDelay: `${index * 70}ms` }}
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
      <h4 className="font-display text-lg font-semibold text-surface-50 mb-2 leading-snug group-hover:text-gradient transition-colors">
        {post.title}
      </h4>
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

export const Blog: React.FC = () => {
  const [posts, setPosts] = useState<BlogPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      setError(null);
      const response = await apiService.getBlogPosts();
      if (cancelled) return;
      if (response.error) {
        setError(response.error);
      } else {
        setPosts(response.data || []);
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const published = posts.filter(p => p.published_at);
  const featured = published[0];
  const recent = published.filter(p => p.id !== featured?.id).slice(0, 6);

  return (
    <section
      id="blog"
      className="relative py-24 sm:py-32 overflow-hidden bg-surface-950"
    >
      <div className="absolute inset-0 bg-gradient-to-b from-surface-950 via-surface-900 to-surface-950 pointer-events-none" />

      <div className="relative z-10 max-w-7xl mx-auto px-6 sm:px-8">
        <div className="text-center mb-16 max-w-2xl mx-auto">
          <span className="inline-block text-xs uppercase tracking-[0.2em] text-accent-violet-400 mb-4">
            Writing
          </span>
          <h2 className="font-display text-4xl sm:text-5xl font-bold text-surface-50 mb-4">
            Notes & <GradientText as="span">articles</GradientText>
          </h2>
          <p className="text-surface-300 text-lg">
            Thoughts on engineering, infrastructure, and adjacent topics.
          </p>
        </div>

        {loading && (
          <div className="space-y-12">
            <div className="h-80 surface-glass rounded-3xl animate-pulse" />
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="h-48 surface-glass rounded-2xl animate-pulse"
                />
              ))}
            </div>
          </div>
        )}

        {error && !loading && (
          <p className="text-center text-surface-400">
            Couldn't load posts right now.
          </p>
        )}

        {!loading && !error && published.length === 0 && (
          <p className="text-center text-surface-400">
            No posts yet — check back soon.
          </p>
        )}

        {!loading && !error && featured && (
          <div className="mb-16">
            <FeaturedCard post={featured} />
          </div>
        )}

        {!loading && !error && recent.length > 0 && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {recent.map((post, i) => (
              <BlogPostCard key={post.id} post={post} index={i} />
            ))}
          </div>
        )}

        {!loading && !error && published.length > 0 && (
          <div className="text-center mt-12">
            <Link
              to="/blog"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-full surface-glass surface-glass-hover text-surface-100"
            >
              View all posts <span>→</span>
            </Link>
          </div>
        )}
      </div>
    </section>
  );
};
