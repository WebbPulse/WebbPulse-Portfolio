import { describe, expect, it } from 'vitest';
import {
  BlogListPage,
  BlogPostPage,
  CaseStudyPage,
  PrivacyPage,
  lazyPageFor,
} from './pages';

describe('lazyPageFor', () => {
  it('maps each split route to its page', () => {
    expect(lazyPageFor('/blog')).toBe(BlogListPage);
    expect(lazyPageFor('/blog/')).toBe(BlogListPage);
    expect(lazyPageFor('/blog/a-post')).toBe(BlogPostPage);
    expect(lazyPageFor('/work/standupless/')).toBe(CaseStudyPage);
    expect(lazyPageFor('/privacy')).toBe(PrivacyPage);
  });

  it('leaves the home page and unknown paths in the main bundle', () => {
    expect(lazyPageFor('/')).toBeUndefined();
    expect(lazyPageFor('/admin')).toBeUndefined();
    expect(lazyPageFor('/work/a/b')).toBeUndefined();
  });
});
