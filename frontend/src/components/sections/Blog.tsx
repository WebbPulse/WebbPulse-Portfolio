import React from 'react';
import { Link } from 'react-router-dom';
import { getPublishedPosts } from '../../content';
import { SectionHeading, Sheet } from '../drawing';
import { PostRow } from './PostRow';

/** The recent posts teaser on the single page site. */
export const Blog: React.FC = () => {
  const published = getPublishedPosts();
  const featured = published[0];
  const recent = published.filter((p) => p.id !== featured?.id).slice(0, 6);

  return (
    <section
      id="blog"
      aria-labelledby="blog-title"
      className="border-b border-line py-20 sm:py-28"
    >
      <Sheet>
        <SectionHeading
          index="06"
          label="Writing"
          id="blog-title"
          title="Notes and articles"
        >
          Thoughts on engineering, infrastructure, and adjacent topics.
        </SectionHeading>

        {published.length === 0 && (
          <p className="text-ink-muted">No posts yet. Check back soon.</p>
        )}

        {featured && (
          <ul className="border-t border-line-strong">
            <PostRow post={featured} featured />
            {recent.map((post) => (
              <PostRow key={post.id} post={post} />
            ))}
          </ul>
        )}

        {published.length > 0 && (
          <div className="mt-8">
            <Link
              to="/blog"
              className="inline-flex items-center gap-2 border border-line-strong px-5 py-2.5 text-sm text-ink transition-colors hover:border-ink"
            >
              View all posts <span aria-hidden="true">→</span>
            </Link>
          </div>
        )}
      </Sheet>
    </section>
  );
};
