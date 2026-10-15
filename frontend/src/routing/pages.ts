import { lazyPage, type LazyPage } from './lazyPage';

/** The blog index, split out of the home page bundle. */
export const BlogListPage = lazyPage(() =>
  import('../components/sections/BlogList').then((m) => m.BlogList)
);

/** A single blog post, split out with the markdown renderer. */
export const BlogPostPage = lazyPage(() =>
  import('../components/sections/BlogPost').then((m) => m.BlogPost)
);

/** A case study, split out with the markdown renderer. */
export const CaseStudyPage = lazyPage(() =>
  import('../pages/CaseStudy').then((m) => m.CaseStudy)
);

/** The privacy policy. */
export const PrivacyPage = lazyPage(() =>
  import('../pages/Privacy').then((m) => m.Privacy)
);

/** Every split page, for the prerender to load before rendering. */
export const LAZY_PAGES: LazyPage[] = [
  BlogListPage,
  BlogPostPage,
  CaseStudyPage,
  PrivacyPage,
];

/** The split page a pathname renders, if it renders one. */
export function lazyPageFor(pathname: string): LazyPage | undefined {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
  if (path === '/blog') return BlogListPage;
  if (/^\/blog\/[^/]+$/.test(path)) return BlogPostPage;
  if (/^\/work\/[^/]+$/.test(path)) return CaseStudyPage;
  if (path === '/privacy') return PrivacyPage;
  return undefined;
}

/** Loads the chunk for the page a pathname renders, if it is split out. */
export async function preloadPageFor(pathname: string): Promise<void> {
  await lazyPageFor(pathname)?.preload();
}
