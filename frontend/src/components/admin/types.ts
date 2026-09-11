import type { SkillCategory, SkillTier } from '../../services/api';

export type {
  BlogPost,
  Category,
  Certification,
  Education,
  Experience,
  Project,
  Skill,
  SkillCategory,
  SkillTier,
} from '../../services/api';

/** Props for the admin panel root. */
export interface AdminPanelProps {
  className?: string;
}

/** Editable fields of a project in the admin form. */
export interface ProjectFormData {
  title: string;
  description: string;
  image: string;
  technologies: string[];
  github_url: string;
  live_url: string;
  featured: boolean;
  display_order: number;
}

/** Editable fields of an experience entry in the admin form. */
export interface ExperienceFormData {
  title: string;
  company: string;
  location: string;
  period: string;
  start_date: string;
  end_date: string;
  description: string;
  technologies: string[];
  achievements: string[];
}

/** Editable fields of a blog post; `published_at` is undefined for a draft. */
export interface BlogPostFormData {
  title: string;
  slug: string;
  content: string;
  excerpt: string;
  read_time: string;
  category_id: number | undefined;
  published_at: string | undefined;
}

/** Editable fields of a blog category. */
export interface CategoryFormData {
  name: string;
  slug: string;
  description: string;
}

/** Editable fields of a skill entry. */
export interface SkillFormData {
  name: string;
  category: SkillCategory;
  tier: SkillTier;
  icon: string;
  order: number;
}

/** Editable fields of an education entry. */
export interface EducationFormData {
  degree: string;
  school: string;
  location: string;
  period: string;
  start_date: string;
  end_date: string;
  description: string;
  order: number;
}

/** Editable fields of a certification entry. */
export interface CertificationFormData {
  name: string;
  issuer: string;
  issued_date: string;
  credential_url: string;
  order: number;
}

/** One of the value cards shown in the About section. */
export interface AboutValueFormData {
  title: string;
  description: string;
  icon: string;
}

/** Editable fields of the singleton site content record. */
export interface SiteContentFormData {
  hero_title: string;
  hero_subtitle: string;
  hero_description: string;
  about_paragraphs: string[];
  about_values: AboutValueFormData[];
  profile_image_url: string;
  resume_url: string;
  email: string;
  github_url: string;
  linkedin_url: string;
  footer_tagline: string;
  project_sort_mode: string;
}

/** Identifies which section the admin panel is showing. */
export type AdminTab =
  | 'projects'
  | 'experience'
  | 'skills'
  | 'education'
  | 'certifications'
  | 'blog'
  | 'categories'
  | 'site-content'
  | 'security';
