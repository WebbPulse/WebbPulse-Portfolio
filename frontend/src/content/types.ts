import type {
  BlogPost,
  Category,
  Certification,
  Education,
  Experience,
  Project as ApiProject,
  Skill,
  SiteContent,
} from '../services/api';

export type {
  AboutValue,
  BlogPost,
  Category,
  Certification,
  Education,
  Experience,
  Skill,
  SkillCategory,
  SkillTier,
  SiteContent,
} from '../services/api';

/** One labelled fact on a project's case study, such as a role or a stack. */
export interface ProjectFact {
  label: string;
  value: string;
}

/** A portfolio project, with the optional fields its case study reads. */
export interface Project extends ApiProject {
  slug?: string;
  summary?: string;
  facts?: ProjectFact[];
  map_node?: string;
}

/** A case study read from `content/work/<slug>.md`. */
export interface CaseStudy {
  slug: string;
  data: Record<string, string>;
  body: string;
}

/** Every structured entity the content module serves. */
export interface ContentSources {
  siteContent: SiteContent;
  projects: Project[];
  experience: Experience[];
  skills: Skill[];
  education: Education[];
  certifications: Certification[];
  categories: Category[];
  posts: BlogPost[];
}
