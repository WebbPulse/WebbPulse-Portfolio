import { useEffect } from 'react';

/** The site name every page title ends with. */
export const SITE_NAME = 'Tyler Webb';

/** The description used when a page does not set its own. */
export const DEFAULT_DESCRIPTION =
  'Tyler Webb, software engineer. Case studies on an issue tracker, a Terraform control plane, a car build tracker and the AWS platform under them.';

/** The title and description one page sets. */
export interface DocumentMeta {
  title?: string | undefined;
  description?: string | undefined;
}

/** The full document title for a page title, or the site title alone. */
export function documentTitle(title?: string): string {
  return title ? `${title} | ${SITE_NAME}` : `${SITE_NAME} | Software Engineer`;
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

/**
 * Sets the document title, the meta description and the Open Graph title and
 * description for the current page.
 */
export function useDocumentMeta({ title, description }: DocumentMeta): void {
  useEffect(() => {
    const fullTitle = documentTitle(title);
    const text = description || DEFAULT_DESCRIPTION;
    document.title = fullTitle;
    setMeta('name', 'description', text);
    setMeta('property', 'og:title', fullTitle);
    setMeta('property', 'og:description', text);
  }, [title, description]);
}
