// The entity shapes come from the API service, which is the single definition
// of what the backend returns. They used to be copied here verbatim, which let
// the two drift: the copy of BlogPost had already diverged from the form type
// that feeds it. Only the admin form and view models are declared below.
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

export interface AdminPanelProps {
  className?: string;
}

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

export interface BlogPostFormData {
  title: string;
  slug: string;
  content: string;
  excerpt: string;
  read_time: string;
  category_id: number | undefined;
  published_at: string | undefined;
}

export interface CategoryFormData {
  name: string;
  slug: string;
  description: string;
}

export interface SkillFormData {
  name: string;
  category: SkillCategory;
  tier: SkillTier;
  icon: string;
  order: number;
}

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

export interface CertificationFormData {
  name: string;
  issuer: string;
  issued_date: string;
  credential_url: string;
  order: number;
}

// Site Content
export interface AboutValueFormData {
  title: string;
  description: string;
  icon: string;
}

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
