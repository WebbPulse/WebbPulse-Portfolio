import { MAP_NODES, nodeCaseStudySlug } from './map';
import type { CaseStudy, Project, ProjectFact } from './types';

/** One external link on a case study, such as the source or the live site. */
export interface CaseStudyLink {
  label: string;
  href: string;
}

/** Everything the case study page renders, merged from both sources. */
export interface CaseStudyView {
  slug: string;
  title: string;
  summary: string;
  role: string;
  period: string;
  stack: string[];
  facts: ProjectFact[];
  body: string;
  hasWriteUp: boolean;
  links: CaseStudyLink[];
  mapNodeId: string | undefined;
}

/** A frontmatter field, treating an empty value as absent. */
const field = (study: CaseStudy | undefined, key: string): string =>
  study?.data[key]?.trim() ?? '';

/** Splits a comma list into trimmed, non-empty items. */
const commaList = (value: string): string[] =>
  value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

/**
 * The map node a case study belongs to: the node named by `mapNode` when it
 * exists, else the first node that links to the case study.
 */
export function mapNodeForCaseStudy(
  slug: string,
  mapNode?: string
): string | undefined {
  if (mapNode && MAP_NODES.some((node) => node.id === mapNode)) return mapNode;
  return MAP_NODES.find((node) => nodeCaseStudySlug(node) === slug)?.id;
}

/**
 * Merges a case study file and a project into one view.
 *
 * Frontmatter wins for title, summary, role, stack and period, and the project
 * fills any gap, so either source alone is enough. Returns undefined when
 * neither exists.
 */
export function resolveCaseStudy(
  slug: string,
  study: CaseStudy | undefined,
  project: Project | undefined
): CaseStudyView | undefined {
  if (!study && !project) return undefined;
  const stack = commaList(field(study, 'stack'));
  const links: CaseStudyLink[] = [];
  if (project?.live_url) {
    links.push({ label: 'Live site', href: project.live_url });
  }
  if (project?.github_url) {
    links.push({ label: 'Source on GitHub', href: project.github_url });
  }
  const body = study?.body.trim() ?? '';
  return {
    slug,
    title: field(study, 'title') || project?.title || slug,
    summary:
      field(study, 'summary') || project?.summary || project?.description || '',
    role: field(study, 'role'),
    period: field(study, 'period'),
    stack: stack.length ? stack : (project?.technologies ?? []),
    facts: project?.facts ?? [],
    body: body || project?.description || '',
    hasWriteUp: body.length > 0,
    links,
    mapNodeId: mapNodeForCaseStudy(
      slug,
      project?.map_node || field(study, 'map_node') || undefined
    ),
  };
}

/** The name a case study goes by in a man page header, such as `STANDUPLESS`. */
export const manName = (slug: string): string =>
  slug.toUpperCase().replace(/[^A-Z0-9]+/g, '-');

/** A case study as a list entry: where it lives and what it is called. */
export interface CaseStudyEntry {
  slug: string;
  title: string;
  summary: string;
}

/**
 * Every case study, in the order its first map node appears and then by slug.
 */
export function listCaseStudies(studies: CaseStudy[]): CaseStudyEntry[] {
  const order = MAP_NODES.map(nodeCaseStudySlug).filter(
    (slug): slug is string => Boolean(slug)
  );
  const rank = (slug: string): number => {
    const index = order.indexOf(slug);
    return index === -1 ? order.length : index;
  };
  return [...studies]
    .sort((a, b) => rank(a.slug) - rank(b.slug) || a.slug.localeCompare(b.slug))
    .map((study) => ({
      slug: study.slug,
      title: field(study, 'title') || study.slug,
      summary: field(study, 'summary'),
    }));
}

/** One row of the work index on the home page. */
export interface WorkEntry {
  slug: string;
  title: string;
  summary: string;
  stack: string[];
  hasWriteUp: boolean;
}

/**
 * The work index: every case study in map order, then every other project
 * with a slug in its own order. Each entry links to `/work/<slug>`.
 */
export function listWork(
  studies: CaseStudy[],
  projects: Project[]
): WorkEntry[] {
  const entries: WorkEntry[] = [];
  const seen = new Set<string>();
  for (const entry of listCaseStudies(studies)) {
    const study = studies.find((s) => s.slug === entry.slug);
    const project = projects.find((p) => p.slug === entry.slug);
    const view = resolveCaseStudy(entry.slug, study, project);
    if (!view) continue;
    seen.add(entry.slug);
    entries.push({
      slug: view.slug,
      title: view.title,
      summary: view.summary,
      stack: view.stack,
      hasWriteUp: view.hasWriteUp,
    });
  }
  for (const project of projects) {
    if (!project.slug || seen.has(project.slug)) continue;
    seen.add(project.slug);
    entries.push({
      slug: project.slug,
      title: project.title,
      summary: project.summary || project.description,
      stack: project.technologies,
      hasWriteUp: false,
    });
  }
  return entries;
}
