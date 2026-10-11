import { describe, expect, it } from 'vitest';
import {
  buildCaseStudies,
  buildPosts,
  loadCaseStudies,
  loadPosts,
  slugFromPath,
} from './loaders';
import type { Category } from './types';

const categories: Category[] = [
  { id: 4, name: 'Cloud Engineering', slug: 'cloud' },
  { id: 9, name: 'Notes', slug: 'notes' },
];

describe('slugFromPath', () => {
  it('drops the folder and the extension', () => {
    expect(slugFromPath('./blog/first-post.md')).toBe('first-post');
    expect(slugFromPath('plain')).toBe('plain');
  });
});

describe('buildPosts', () => {
  it('maps frontmatter onto a published post', () => {
    const [post] = buildPosts(
      {
        './blog/a.md': [
          '---',
          'title: First',
          'slug: first-post',
          'excerpt: Short',
          'category: cloud',
          'published_at: 2026-10-01T00:00:00Z',
          'read_time: 4 min read',
          'id: 12',
          '---',
          'Body text',
        ].join('\n'),
      },
      categories
    );

    expect(post).toEqual({
      id: 12,
      title: 'First',
      slug: 'first-post',
      content: 'Body text',
      excerpt: 'Short',
      read_time: '4 min read',
      published_at: '2026-10-01T00:00:00Z',
      created_at: '2026-10-01T00:00:00Z',
      updated_at: undefined,
      category_id: 4,
      category: { id: 4, name: 'Cloud Engineering', slug: 'cloud' },
    });
  });

  it('falls back to the file name, path order ids and the slug as title', () => {
    const posts = buildPosts(
      { './blog/b.md': 'Only body', './blog/a.md': '---\nid: zero\n---\nA' },
      categories
    );

    expect(posts.map((p) => [p.id, p.slug, p.title])).toEqual([
      [1, 'a', 'a'],
      [2, 'b', 'b'],
    ]);
    expect(posts[0]?.category).toBeUndefined();
    expect(posts[0]?.created_at).toBe('');
  });

  it('matches a category by name and ignores an unknown one', () => {
    const posts = buildPosts(
      {
        './blog/a.md': '---\ncategory: notes\n---\n',
        './blog/b.md': '---\ncategory: Cloud Engineering\n---\n',
        './blog/c.md': '---\ncategory: missing\n---\n',
      },
      categories
    );

    expect(posts.map((p) => p.category_id)).toEqual([9, 4, undefined]);
  });

  it('drops the publish date from a draft', () => {
    const [post] = buildPosts(
      { './blog/a.md': '---\ndraft: true\npublished_at: 2026-10-01\n---\n' },
      categories
    );

    expect(post?.published_at).toBeUndefined();
  });
});

describe('buildCaseStudies', () => {
  it('keeps frontmatter and body keyed by slug', () => {
    const studies = buildCaseStudies({
      './work/standupless.md': '---\nrole: Founder\n---\nStory',
      './work/other.md': '---\nslug: renamed\n---\n',
    });

    expect(studies).toEqual([
      { slug: 'renamed', data: { slug: 'renamed' }, body: '' },
      { slug: 'standupless', data: { role: 'Founder' }, body: 'Story' },
    ]);
  });
});

describe('committed markdown', () => {
  it('parses every committed post and case study', () => {
    expect(Array.isArray(loadPosts(categories))).toBe(true);
    expect(Array.isArray(loadCaseStudies())).toBe(true);
  });
});
