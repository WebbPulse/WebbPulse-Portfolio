import React from 'react';
import { Link } from 'react-router-dom';
import type { BlogPost } from '../../content';

/** A published date in short form, empty when the post has none. */
function formatDate(iso?: string): string {
  return iso
    ? new Date(iso).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        timeZone: 'UTC',
      })
    : '';
}

/**
 * One post as a row of an index: date, title and excerpt, category and read
 * time. The featured variant gives the title more room.
 */
export const PostRow: React.FC<{
  post: BlogPost;
  featured?: boolean;
  headingLevel?: 'h2' | 'h3';
}> = ({ post, featured = false, headingLevel: Heading = 'h3' }) => (
  <li className="border-b border-line">
    <Link
      to={`/blog/${post.slug}`}
      className="group grid gap-2 py-6 transition-colors hover:bg-accent-soft sm:grid-cols-12 sm:gap-6 sm:px-3 sm:-mx-3"
    >
      <div className="font-mono text-xs text-ink-muted tabular-nums sm:col-span-2 sm:pt-1.5">
        <time dateTime={post.published_at}>
          {formatDate(post.published_at)}
        </time>
      </div>
      <div className="sm:col-span-8">
        {featured && (
          <span className="mono-label mb-2 block text-accent">Latest</span>
        )}
        <Heading
          className={`font-semibold tracking-tight text-ink group-hover:text-accent transition-colors ${featured ? 'text-2xl sm:text-3xl' : 'text-lg'}`}
        >
          {post.title}
        </Heading>
        {post.excerpt && (
          <p
            className={`mt-2 leading-relaxed text-ink-muted ${featured ? 'text-base sm:text-lg' : 'text-sm'}`}
          >
            {post.excerpt}
          </p>
        )}
      </div>
      <div className="flex items-center gap-3 sm:col-span-2 sm:flex-col sm:items-end sm:gap-1 sm:pt-1.5">
        {post.category && (
          <span className="mono-label text-ink">{post.category.name}</span>
        )}
        {post.read_time && (
          <span className="font-mono text-xs text-ink-muted">
            {post.read_time}
          </span>
        )}
      </div>
    </Link>
  </li>
);

export default PostRow;
