import { buildCaseStudies } from './loaders';
import type { CaseStudy } from './types';

const workFiles = import.meta.glob<string>('./work/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const studies = buildCaseStudies(workFiles);

/** A case study with its full write-up, for the case study page chunk. */
export function findCaseStudy(slug: string): CaseStudy | undefined {
  return studies.find((study) => study.slug === slug);
}
