import { buildPosts } from './loaders';

const blogFiles = import.meta.glob<string>('./blog/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const posts = buildPosts(blogFiles, []);

/** The markdown body of a post, for the post page chunk. */
export function findPostContent(slug: string): string | undefined {
  return posts.find((post) => post.slug === slug)?.content;
}
