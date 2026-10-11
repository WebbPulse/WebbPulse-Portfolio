import type {
  BlogPost,
  CaseStudy,
  Category,
  Certification,
  ContentSources,
  Education,
  Experience,
  Project,
  SiteContent,
  Skill,
} from './types';

type Direction = 'asc' | 'desc';
type SortSpec<T> = [keyof T, Direction];

/** Compares two field values, placing a missing value last either way. */
function compareValues(a: unknown, b: unknown, direction: Direction): number {
  const aMissing = a === undefined || a === null;
  const bMissing = b === undefined || b === null;
  if (aMissing || bMissing) {
    return Number(aMissing) - Number(bMissing);
  }
  const order =
    typeof a === 'number' && typeof b === 'number'
      ? a - b
      : typeof a === 'boolean' && typeof b === 'boolean'
        ? Number(a) - Number(b)
        : String(a).localeCompare(String(b));
  return direction === 'asc' ? order : -order;
}

/**
 * Sorts a copy of `items` by field specs, most significant first.
 *
 * Mirrors the API's ordering, so ties fall back to `id` and a listing reads the
 * same as it did when it was served.
 */
export function orderBy<T extends { id: number }>(
  items: readonly T[],
  ...specs: SortSpec<T>[]
): T[] {
  return [...items].sort((a, b) => {
    for (const [key, direction] of specs) {
      const result = compareValues(a[key], b[key], direction);
      if (result !== 0) return result;
    }
    return a.id - b.id;
  });
}

/** The read API over one set of content sources. */
export interface ContentSelectors {
  getSiteContent: () => SiteContent;
  getProjects: () => Project[];
  getProjectBySlug: (slug: string) => Project | undefined;
  getExperience: () => Experience[];
  getSkills: () => Skill[];
  getEducation: () => Education[];
  getCertifications: () => Certification[];
  getCategories: () => Category[];
  getPublishedPosts: () => BlogPost[];
  getPostBySlug: (slug: string) => BlogPost | undefined;
  getCaseStudy: (slug: string) => CaseStudy | undefined;
}

/**
 * Builds the selectors over `sources` and the parsed case studies.
 *
 * Every list comes back sorted the way the API sorted it, and only posts with a
 * `published_at` are public.
 */
export function createSelectors(
  sources: ContentSources,
  caseStudies: CaseStudy[] = []
): ContentSelectors {
  const projects = orderBy(
    sources.projects,
    ['featured', 'desc'],
    ['display_order', 'asc'],
    ['created_at', 'desc']
  );
  const published = orderBy(
    sources.posts.filter((p) => Boolean(p.published_at)),
    ['published_at', 'desc']
  );
  const experience = orderBy(sources.experience, ['start_date', 'desc']);
  const skills = orderBy(sources.skills, ['order', 'asc'], ['name', 'asc']);
  const education = orderBy(
    sources.education,
    ['order', 'asc'],
    ['start_date', 'desc']
  );
  const certifications = orderBy(
    sources.certifications,
    ['order', 'asc'],
    ['issued_date', 'desc']
  );
  const categories = orderBy(sources.categories, ['name', 'asc']);

  return {
    getSiteContent: () => sources.siteContent,
    getProjects: () => projects,
    getProjectBySlug: (slug) => projects.find((p) => p.slug === slug),
    getExperience: () => experience,
    getSkills: () => skills,
    getEducation: () => education,
    getCertifications: () => certifications,
    getCategories: () => categories,
    getPublishedPosts: () => published,
    getPostBySlug: (slug) => published.find((p) => p.slug === slug),
    getCaseStudy: (slug) => caseStudies.find((c) => c.slug === slug),
  };
}
