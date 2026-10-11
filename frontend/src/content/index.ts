import { categories } from './categories';
import { certifications } from './certifications';
import { education } from './education';
import { experience } from './experience';
import { loadCaseStudies, loadPosts } from './loaders';
import { projects } from './projects';
import { createSelectors } from './selectors';
import { siteContent } from './site';
import { skills } from './skills';

export type * from './types';
export { createSelectors } from './selectors';
export { parseFrontmatter } from './frontmatter';

/** The selectors over the content committed to this repository. */
export const content = createSelectors(
  {
    siteContent,
    projects,
    experience,
    skills,
    education,
    certifications,
    categories,
    posts: loadPosts(categories),
  },
  loadCaseStudies()
);

export const {
  getSiteContent,
  getProjects,
  getProjectBySlug,
  getExperience,
  getSkills,
  getEducation,
  getCertifications,
  getCategories,
  getPublishedPosts,
  getPostBySlug,
  getCaseStudy,
} = content;
