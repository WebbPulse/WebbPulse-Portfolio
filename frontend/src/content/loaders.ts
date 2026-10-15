import { parseFrontmatter } from './frontmatter';
import type { BlogPost, CaseStudy, Category } from './types';

const blogFiles = import.meta.glob<string>('./blog/*.md', {
  query: '?raw',
  import: 'default',
  eager: true,
});

const workFiles = import.meta.glob<string>('./work/*.md', {
  query: '?raw&frontmatter',
  import: 'default',
  eager: true,
});

/** The file name of a content path without its folder or `.md` extension. */
export function slugFromPath(path: string): string {
  const name = path.split('/').pop() ?? path;
  return name.replace(/\.md$/, '');
}

/** Reads a frontmatter field, treating an empty value as absent. */
function field(data: Record<string, string>, key: string): string | undefined {
  const value = data[key];
  return value === undefined || value === '' ? undefined : value;
}

/** Finds the category a post's `category` frontmatter names by slug or name. */
function resolveCategory(
  categories: Category[],
  value: string | undefined
): Category | undefined {
  if (value === undefined) return undefined;
  const wanted = value.toLowerCase();
  return categories.find(
    (c) => c.slug === wanted || c.name.toLowerCase() === wanted
  );
}

/**
 * Builds blog posts from raw markdown files keyed by path.
 *
 * The slug comes from frontmatter or else the file name, a post marked
 * `draft: true` loses its `published_at`, and ids follow path order unless the
 * frontmatter sets one.
 */
export function buildPosts(
  files: Record<string, string>,
  categories: Category[]
): BlogPost[] {
  return Object.keys(files)
    .sort()
    .map((path, index) => {
      const { data, body } = parseFrontmatter(files[path] ?? '');
      const slug = field(data, 'slug') ?? slugFromPath(path);
      const draft = field(data, 'draft') === 'true';
      const publishedAt = draft ? undefined : field(data, 'published_at');
      const category = resolveCategory(categories, field(data, 'category'));
      const id = Number(field(data, 'id'));
      return {
        id: Number.isInteger(id) && id > 0 ? id : index + 1,
        title: field(data, 'title') ?? slug,
        slug,
        content: body,
        excerpt: field(data, 'excerpt'),
        read_time: field(data, 'read_time'),
        published_at: publishedAt,
        created_at: field(data, 'created_at') ?? publishedAt ?? '',
        updated_at: field(data, 'updated_at'),
        category_id: category?.id,
        ...(category
          ? {
              category: {
                id: category.id,
                name: category.name,
                slug: category.slug,
              },
            }
          : {}),
      };
    });
}

/** Builds case studies from raw markdown files keyed by path. */
export function buildCaseStudies(files: Record<string, string>): CaseStudy[] {
  return Object.keys(files)
    .sort()
    .map((path) => {
      const { data, body } = parseFrontmatter(files[path] ?? '');
      return { slug: field(data, 'slug') ?? slugFromPath(path), data, body };
    });
}

/** Every blog post file under `content/blog`, parsed against `categories`. */
export function loadPosts(categories: Category[]): BlogPost[] {
  return buildPosts(blogFiles, categories);
}

/**
 * Every case study file under `content/work`, frontmatter only. The bodies
 * stay out of the main bundle; `has_write_up` says whether one exists, and
 * `caseStudyBodies` loads them for the case study page.
 */
export function loadCaseStudies(): CaseStudy[] {
  return buildCaseStudies(workFiles);
}
