import {
  createApiClient,
  createEnvelopeClient,
  type ApiEnvelope,
  type EnvelopeClient,
} from '@webbpulse/api-client';
import { loadAppConfig } from '@webbpulse/config';

const config = loadAppConfig(import.meta.env, {
  defaultApiBaseUrl:
    import.meta.env.MODE === 'production'
      ? 'https://api.portfolio.webbpulse.com/api/v1'
      : 'http://localhost:8000/api/v1',
  defaultAppName: 'WebbPulse Portfolio',
});

/** Base URL of this application's API, from the resolved app config. */
export const API_BASE_URL = config.apiBaseUrl;

/** A portfolio project as the API returns it. */
export interface Project {
  id: number;
  title: string;
  description: string;
  image: string;
  technologies: string[];
  github_url?: string;
  live_url?: string;
  featured: boolean;
  display_order: number;
  created_at: string;
}

/** A work history entry as the API returns it. */
export interface Experience {
  id: number;
  title: string;
  company: string;
  location: string;
  period: string;
  start_date: string;
  end_date?: string;
  description: string;
  technologies: string[];
  achievements: string[];
  created_at: string;
}

/** A blog post as the API returns it; `published_at` is absent on a draft. */
export interface BlogPost {
  id: number;
  title: string;
  slug: string;
  content: string;
  excerpt?: string | undefined;
  read_time?: string | undefined;
  published_at?: string | undefined;
  created_at: string;
  updated_at?: string | undefined;
  category_id?: number | undefined;
  category?: {
    id: number;
    name: string;
    slug: string;
  };
}

/** A blog category as the API returns it. */
export interface Category {
  id: number;
  name: string;
  slug: string;
  description?: string;
}

/** The discipline a skill is grouped under. */
export type SkillCategory =
  'frontend' | 'backend' | 'devops' | 'cloud' | 'networking' | 'other';
/** How strong a skill is, from strongest to weakest. */
export type SkillTier = 'core' | 'working' | 'familiar';

/** A skill as the API returns it. */
export interface Skill {
  id: number;
  name: string;
  category: SkillCategory;
  tier: SkillTier;
  icon?: string;
  order: number;
  created_at: string;
}

/** An education entry as the API returns it. */
export interface Education {
  id: number;
  degree: string;
  school: string;
  location: string;
  period: string;
  start_date: string;
  end_date?: string | null;
  description?: string | null;
  order: number;
  created_at: string;
}

/** A certification as the API returns it. */
export interface Certification {
  id: number;
  name: string;
  issuer: string;
  issued_date: string;
  credential_url?: string | null;
  order: number;
  created_at: string;
}

/** One value card inside the site content record. */
export interface AboutValue {
  title: string;
  description: string;
  icon?: string | null;
}

/** The singleton record backing the public site's copy. */
export interface SiteContent {
  id: number;
  hero_subtitle: string;
  hero_description: string;
  about_paragraphs: string[];
  about_values: AboutValue[];
  profile_image_url?: string | null;
  resume_url?: string | null;
  email?: string | null;
  github_url?: string | null;
  linkedin_url?: string | null;
  footer_tagline?: string | null;
  project_sort_mode: string;
  created_at: string;
  updated_at?: string | null;
}

/**
 * The envelope every call site in this application reads.
 *
 * The package's `ApiEnvelope`, so `data` is typed `T | null` as the error path
 * always returned.
 */
export type ApiResponse<T> = ApiEnvelope<T>;

/**
 * Typed client for the portfolio API's public, anonymous routes.
 *
 * Failures resolve to the `{ data, error }` envelope without logging, so a
 * missing optional figure never surfaces as a console error.
 */
export class ApiService {
  private readonly client: EnvelopeClient;

  constructor(baseUrl: string = API_BASE_URL) {
    this.client = createEnvelopeClient(
      createApiClient({ baseUrl, credentials: 'include' })
    );
  }

  /** Live public system figures, cached server side for about 15 minutes. */
  async getPublicFigures(): Promise<ApiResponse<PublicFiguresResponse>> {
    return this.client.get<PublicFiguresResponse>('/public/figures');
  }
}

/** Shared ApiService instance used across the application. */
export const apiService = new ApiService();

/** One live public system figure, such as a latest release or a site status. */
export interface PublicFigure {
  id: string;
  label: string;
  value: string;
  as_of: string;
  source: string;
  url?: string;
}

/** The body of `GET /api/v1/public/figures`. */
export interface PublicFiguresResponse {
  figures: PublicFigure[];
}
