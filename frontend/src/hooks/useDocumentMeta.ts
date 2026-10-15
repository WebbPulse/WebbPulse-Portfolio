import { createContext, useContext, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/** The site name every page title ends with. */
export const SITE_NAME = 'Tyler Webb';

/** The public origin canonical links and the sitemap point at. */
export const SITE_ORIGIN = 'https://portfolio.webbpulse.com';

/** The description used when a page does not set its own. */
export const DEFAULT_DESCRIPTION =
  'Tyler Webb, software engineer. Case studies on an issue tracker, a Terraform control plane, a car build tracker and the AWS platform under them.';

/** The title and description one page sets, and whether search should skip it. */
export interface DocumentMeta {
  title?: string | undefined;
  description?: string | undefined;
  noindex?: boolean | undefined;
}

/** The resolved metadata of one page, as the prerender writes it into the head. */
export interface PageMeta {
  title: string;
  description: string;
  noindex: boolean;
}

/** A receiver for one page's metadata. */
export type MetaSink = (meta: PageMeta) => void;

/** Receives each page's metadata during the build-time prerender. */
export const DocumentMetaSink = createContext<MetaSink | null>(null);

/** The full document title for a page title, or the site title alone. */
export function documentTitle(title?: string): string {
  return title ? `${title} | ${SITE_NAME}` : `${SITE_NAME} | Software Engineer`;
}

/** The canonical URL of a path, without a trailing slash except for the root. */
export function canonicalUrl(pathname: string): string {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
  return `${SITE_ORIGIN}${path || '/'}`;
}

/** Sets the content of a meta tag, creating the tag when it is missing. */
function setMeta(attribute: 'name' | 'property', key: string, value: string) {
  let tag = document.head.querySelector<HTMLMetaElement>(
    `meta[${attribute}="${key}"]`
  );
  if (!tag) {
    tag = document.createElement('meta');
    tag.setAttribute(attribute, key);
    document.head.appendChild(tag);
  }
  tag.setAttribute('content', value);
}

/** Sets the canonical link, or removes it when `href` is null. */
function setCanonical(href: string | null) {
  let link = document.head.querySelector<HTMLLinkElement>(
    'link[rel="canonical"]'
  );
  if (!href) {
    link?.remove();
    return;
  }
  if (!link) {
    link = document.createElement('link');
    link.setAttribute('rel', 'canonical');
    document.head.appendChild(link);
  }
  link.setAttribute('href', href);
}

/** Sets the robots meta tag to noindex, or removes it. */
function setNoindex(noindex: boolean) {
  if (noindex) setMeta('name', 'robots', 'noindex');
  else document.head.querySelector('meta[name="robots"]')?.remove();
}

/**
 * Sets the document title, description, canonical link and the Open Graph
 * and Twitter tags for the current page, and hands the same metadata to the
 * prerender when one is listening.
 */
export function useDocumentMeta({
  title,
  description,
  noindex = false,
}: DocumentMeta): void {
  const sink = useContext(DocumentMetaSink);
  const { pathname } = useLocation();
  const fullTitle = documentTitle(title);
  const text = description || DEFAULT_DESCRIPTION;
  sink?.({ title: fullTitle, description: text, noindex });

  useEffect(() => {
    const url = canonicalUrl(pathname);
    document.title = fullTitle;
    setMeta('name', 'description', text);
    setMeta('property', 'og:title', fullTitle);
    setMeta('property', 'og:description', text);
    setMeta('property', 'og:url', url);
    setMeta('name', 'twitter:title', fullTitle);
    setMeta('name', 'twitter:description', text);
    setCanonical(noindex ? null : url);
    setNoindex(noindex);
  }, [fullTitle, text, noindex, pathname]);
}
