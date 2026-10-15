import { StrictMode } from 'react';
import { renderToString } from 'react-dom/server';
import { StaticRouter } from 'react-router-dom';
import { AppRoutes } from './App';
import { getProjects, getPublishedPosts } from './content';
import { loadCaseStudies } from './content/loaders';
import {
  DocumentMetaSink,
  SITE_ORIGIN,
  type MetaSink,
  type PageMeta,
} from './hooks';

export { SITE_ORIGIN };

/** The path the not found page is prerendered at. */
export const NOT_FOUND_PATH = '/404';

/** One prerendered page: its markup and the metadata its head carries. */
export interface RenderedPage {
  html: string;
  meta: PageMeta;
}

/** Every public path to prerender, the not found page last. */
export function prerenderRoutes(): string[] {
  const work = new Set<string>();
  for (const study of loadCaseStudies()) work.add(study.slug);
  for (const project of getProjects()) {
    if (project.slug) work.add(project.slug);
  }
  return [
    '/',
    '/blog',
    '/privacy',
    ...[...work].map((slug) => `/work/${slug}`),
    ...getPublishedPosts().map((post) => `/blog/${post.slug}`),
    NOT_FOUND_PATH,
  ];
}

/** Renders one path to HTML with the metadata its page set. */
export function render(url: string): RenderedPage {
  const captured: { meta?: PageMeta } = {};
  const sink: MetaSink = (meta) => {
    captured.meta = meta;
  };
  const html = renderToString(
    <StrictMode>
      <StaticRouter location={url}>
        <DocumentMetaSink.Provider value={sink}>
          <AppRoutes />
        </DocumentMetaSink.Provider>
      </StaticRouter>
    </StrictMode>
  );
  if (!captured.meta) {
    throw new Error(`No page metadata was set while rendering ${url}`);
  }
  return { html, meta: captured.meta };
}
