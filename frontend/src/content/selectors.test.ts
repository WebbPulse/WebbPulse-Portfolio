import { describe, expect, it } from 'vitest';
import { createSelectors, orderBy } from './selectors';
import type {
  BlogPost,
  Certification,
  ContentSources,
  Education,
  Experience,
  Project,
  SiteContent,
  Skill,
} from './types';

function post(id: number, slug: string, published_at?: string): BlogPost {
  return {
    id,
    title: slug,
    slug,
    content: '',
    created_at: '2026-01-01',
    ...(published_at ? { published_at } : {}),
  };
}

function project(
  id: number,
  featured: boolean,
  display_order: number,
  slug?: string
): Project {
  return {
    id,
    title: `Project ${id}`,
    description: '',
    image: '',
    technologies: [],
    featured,
    display_order,
    created_at: '2026-01-01',
    ...(slug ? { slug } : {}),
  };
}

const sources: ContentSources = {
  siteContent: { id: 1 } as SiteContent,
  projects: [
    project(1, false, 0, 'plain'),
    project(2, true, 2),
    project(3, true, 1, 'top'),
  ],
  experience: [
    { id: 1, start_date: '2020-01-01' },
    { id: 2, start_date: '2024-01-01' },
  ] as Experience[],
  skills: [
    { id: 1, name: 'Zig', order: 1 },
    { id: 2, name: 'Go', order: 1 },
    { id: 3, name: 'Rust', order: 0 },
  ] as Skill[],
  education: [
    { id: 1, order: 0, start_date: '2010-01-01' },
    { id: 2, order: 0, start_date: '2015-01-01' },
  ] as Education[],
  certifications: [
    { id: 1, order: 1, issued_date: '2025-01-01' },
    { id: 2, order: 0, issued_date: '2020-01-01' },
  ] as Certification[],
  categories: [
    { id: 1, name: 'Zeta', slug: 'zeta' },
    { id: 2, name: 'Alpha', slug: 'alpha' },
  ],
  posts: [
    post(1, 'old', '2026-01-01'),
    post(2, 'draft'),
    post(3, 'new', '2026-06-01'),
  ],
};

describe('orderBy', () => {
  it('sorts missing values last and breaks ties by id', () => {
    const items: { id: number; rank?: number }[] = [
      { id: 3, rank: 1 },
      { id: 1 },
      { id: 2, rank: 1 },
      { id: 4, rank: 0 },
    ];

    expect(orderBy(items, ['rank', 'desc']).map((i) => i.id)).toEqual([
      2, 3, 4, 1,
    ]);
    expect(orderBy(items, ['rank', 'asc']).map((i) => i.id)).toEqual([
      4, 2, 3, 1,
    ]);
  });

  it('leaves the input untouched', () => {
    const items = [{ id: 2 }, { id: 1 }];
    orderBy(items);

    expect(items.map((i) => i.id)).toEqual([2, 1]);
  });
});

describe('createSelectors', () => {
  const select = createSelectors(sources, [
    { slug: 'top', data: { role: 'Lead' }, body: 'Story' },
  ]);

  it('orders every list the way the API did', () => {
    expect(select.getProjects().map((p) => p.id)).toEqual([3, 2, 1]);
    expect(select.getExperience().map((e) => e.id)).toEqual([2, 1]);
    expect(select.getSkills().map((s) => s.name)).toEqual([
      'Rust',
      'Go',
      'Zig',
    ]);
    expect(select.getEducation().map((e) => e.id)).toEqual([2, 1]);
    expect(select.getCertifications().map((c) => c.id)).toEqual([2, 1]);
    expect(select.getCategories().map((c) => c.slug)).toEqual([
      'alpha',
      'zeta',
    ]);
  });

  it('serves only published posts, newest first', () => {
    expect(select.getPublishedPosts().map((p) => p.slug)).toEqual([
      'new',
      'old',
    ]);
    expect(select.getPostBySlug('old')?.id).toBe(1);
    expect(select.getPostBySlug('draft')).toBeUndefined();
  });

  it('finds projects and case studies by slug', () => {
    expect(select.getSiteContent()).toBe(sources.siteContent);
    expect(select.getProjectBySlug('top')?.id).toBe(3);
    expect(select.getProjectBySlug('nope')).toBeUndefined();
    expect(select.getCaseStudy('top')?.body).toBe('Story');
    expect(createSelectors(sources).getCaseStudy('top')).toBeUndefined();
  });
});
