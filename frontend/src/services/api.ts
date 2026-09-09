// API service for communicating with the backend.
//
// The transport is @webbpulse/api-client and the configuration is
// @webbpulse/config, both from the org CodeArtifact repository. The shared
// client rejects on a non 2xx and every call site in this application reads a
// `{ data, error }` envelope instead, so an adapter sits between the two.
//
// That adapter used to be a private helper in this file. It is now
// `createEnvelopeClient` from the package, which is the same conversion typed
// and tested once rather than copied per application. The only visible
// difference is that the package types `data` as `T | null`, which is what the
// error path always returned; the local version declared `data: T` and wrote
// `null as T` into it, so every call site read a value the type said could not
// be null.
import {
  ApiError,
  createApiClient,
  createEnvelopeClient,
  getWebbPulseError,
  type ApiEnvelope,
  type EnvelopeClient,
} from '@webbpulse/api-client';
import { loadAppConfig } from '@webbpulse/config';
import { TokenStore } from '@webbpulse/auth';

/** Key the auth token is stored under. Unchanged, so sessions survive deploy. */
const TOKEN_STORAGE_KEY = 'authToken';

const config = loadAppConfig(import.meta.env, {
  // Stated here rather than defaulted inside the package: production talks to
  // the deployed API and everything else to a local backend, which is the
  // behaviour the previous hand rolled getApiBaseUrl had.
  defaultApiBaseUrl:
    import.meta.env.MODE === 'production'
      ? 'https://api.webbpulse.com/api/v1'
      : 'http://localhost:8000/api/v1',
  defaultAppName: 'WebbPulse Portfolio',
});

export const API_BASE_URL = config.apiBaseUrl;

/**
 * Logs a failed request with the fields the backend's error envelope carries.
 *
 * Every WebbPulse backend renders one error body, so a failure arrives with a
 * `message`, a `status` and the `request_id` that joins this line to the
 * CloudWatch logs and the trace for the same request. `getWebbPulseError`
 * reads those without this file having to know that the body is snake case, or
 * having to re-implement the shape check.
 *
 * `errorCode` is logged when the backend sends one. Portfolio's `create_app`
 * has not opted into `error_codes` yet, so it is `undefined` in practice today
 * and the field is simply omitted rather than logged as empty.
 */
function logApiFailure(error: unknown): void {
  if (error instanceof ApiError) {
    const { message, errorCode, requestId, status } = getWebbPulseError(error);
    console.error('API request failed:', {
      message,
      status,
      ...(errorCode === undefined ? {} : { errorCode }),
      ...(requestId === undefined ? {} : { requestId }),
    });
    return;
  }
  // A network failure, a timeout or an abort. There is no envelope to read, so
  // the thrown value is all there is to report.
  console.error('API request failed:', error);
}

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

export interface BlogPost {
  id: number;
  title: string;
  slug: string;
  content: string;
  excerpt?: string | undefined;
  read_time?: string | undefined;
  // Absent until the post is published, and the admin form carries it as
  // `undefined` for a draft, so the optionality has to be explicit.
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

export interface Category {
  id: number;
  name: string;
  slug: string;
  description?: string;
}

export type SkillCategory =
  | 'frontend'
  | 'backend'
  | 'devops'
  | 'cloud'
  | 'networking'
  | 'other';
export type SkillTier = 'core' | 'working' | 'familiar';

export interface Skill {
  id: number;
  name: string;
  category: SkillCategory;
  tier: SkillTier;
  icon?: string;
  order: number;
  created_at: string;
}

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

export interface Certification {
  id: number;
  name: string;
  issuer: string;
  issued_date: string;
  credential_url?: string | null;
  order: number;
  created_at: string;
}

export interface AboutValue {
  title: string;
  description: string;
  icon?: string | null;
}

export interface SiteContent {
  id: number;
  hero_title: string;
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

export interface UserLogin {
  username: string;
  password: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

/**
 * The envelope every call site in this application reads.
 *
 * The package's `ApiEnvelope` rather than a local declaration, so there is one
 * definition of the shape. `data` is `T | null`: it was always null on the
 * error path, and saying so makes the check the compiler's job rather than the
 * reader's. `status`, `requestId` and `cause` come along with it, which the
 * hand rolled envelope did not carry.
 */
export type ApiResponse<T> = ApiEnvelope<T>;

export class ApiService {
  private readonly client: EnvelopeClient;
  private readonly tokenStore: TokenStore;

  constructor(baseUrl: string = API_BASE_URL) {
    // TokenStore degrades to an in memory store when localStorage throws,
    // which Safari in private mode does, so reading a token cannot break the
    // application on load.
    this.tokenStore = new TokenStore(TOKEN_STORAGE_KEY);
    this.client = createEnvelopeClient(
      createApiClient({
        baseUrl,
        // The client defaults to credentials: 'include', which the staging
        // access gate needs: its CloudFront signed cookies are set on the
        // staging apex, so a request from the www host to the API host only
        // carries them when credentials are included. Stated explicitly so it
        // is not lost to a future default change.
        credentials: 'include',
        // Read synchronously on every request, which is what the client
        // requires.
        getAuthToken: () => this.tokenStore.get(),
        // The API reissues a token in a response header after a username
        // change.
        onTokenRefresh: token => {
          this.tokenStore.set(token);
        },
      }),
      {
        // The package logs nothing of its own, so reporting stays a decision
        // this application makes. Keeping console.error preserves what the
        // hand rolled adapter did; the hook is where a real reporter goes.
        onError: error => {
          logApiFailure(error);
        },
      }
    );
  }

  private request<T>(
    endpoint: string,
    options: { method?: string; body?: unknown } = {}
  ): Promise<ApiResponse<T>> {
    const method = options.method ?? 'GET';
    return this.client.request<T>(method, endpoint, {
      ...(options.body === undefined ? {} : { body: options.body }),
    });
  }

  // Authentication methods
  async login(credentials: UserLogin): Promise<ApiResponse<Token>> {
    const response = await this.request<Token>('/admin/login', {
      method: 'POST',
      body: credentials,
    });

    if (response.data) {
      this.tokenStore.set(response.data.access_token);
    }

    return response;
  }

  logout(): void {
    this.tokenStore.clear();
  }

  isAuthenticated(): boolean {
    // Read through on every call rather than caching in a field. The previous
    // cached copy went stale whenever another tab signed in or out.
    const token = this.tokenStore.get();
    return token !== null && token !== '';
  }

  // Projects API
  async getProjects(
    featuredOnly: boolean = false
  ): Promise<ApiResponse<Project[]>> {
    // The query goes through the client rather than being concatenated into
    // the path. The previous form built `/projects?featured_only=true/`, which
    // put the trailing slash inside the query string, so the filter only ever
    // worked by the backend ignoring an unparsed value.
    return this.client.get<Project[]>('/projects/', {
      ...(featuredOnly ? { query: { featured_only: true } } : {}),
    });
  }

  async getProject(id: number): Promise<ApiResponse<Project>> {
    return this.request<Project>(`/projects/${id}`);
  }

  // Experience API
  async getExperience(): Promise<ApiResponse<Experience[]>> {
    return this.request<Experience[]>('/experience/');
  }

  async getExperienceEntry(id: number): Promise<ApiResponse<Experience>> {
    return this.request<Experience>(`/experience/${id}`);
  }

  // Admin CRUD operations for Projects
  async createProject(
    project: Omit<Project, 'id' | 'created_at'>
  ): Promise<ApiResponse<Project>> {
    return this.request<Project>('/projects/', {
      method: 'POST',
      body: project,
    });
  }

  async updateProject(
    id: number,
    project: Partial<Project>
  ): Promise<ApiResponse<Project>> {
    return this.request<Project>(`/projects/${id}`, {
      method: 'PUT',
      body: project,
    });
  }

  async deleteProject(id: number): Promise<ApiResponse<{ message: string }>> {
    return this.request<{ message: string }>(`/projects/${id}`, {
      method: 'DELETE',
    });
  }

  // Admin CRUD operations for Experience
  async createExperience(
    experience: Omit<Experience, 'id' | 'created_at'>
  ): Promise<ApiResponse<Experience>> {
    return this.request<Experience>('/experience/', {
      method: 'POST',
      body: experience,
    });
  }

  async updateExperience(
    id: number,
    experience: Partial<Experience>
  ): Promise<ApiResponse<Experience>> {
    return this.request<Experience>(`/experience/${id}`, {
      method: 'PUT',
      body: experience,
    });
  }

  async deleteExperience(
    id: number
  ): Promise<ApiResponse<{ message: string }>> {
    return this.request<{ message: string }>(`/experience/${id}`, {
      method: 'DELETE',
    });
  }

  // Blog Posts API
  async getBlogPosts(): Promise<ApiResponse<BlogPost[]>> {
    return this.request<BlogPost[]>('/posts/');
  }

  async getAdminBlogPosts(): Promise<ApiResponse<BlogPost[]>> {
    return this.request<BlogPost[]>('/posts/admin');
  }

  async getBlogPost(id: number): Promise<ApiResponse<BlogPost>> {
    return this.request<BlogPost>(`/posts/${id}`);
  }

  async getBlogPostBySlug(slug: string): Promise<ApiResponse<BlogPost>> {
    return this.request<BlogPost>(`/posts/${slug}`);
  }

  // Admin CRUD operations for Blog Posts
  async createBlogPost(
    post: Omit<BlogPost, 'id' | 'created_at' | 'updated_at'>
  ): Promise<ApiResponse<BlogPost>> {
    return this.request<BlogPost>('/posts/admin', {
      method: 'POST',
      body: post,
    });
  }

  async updateBlogPost(
    id: number,
    post: Partial<BlogPost>
  ): Promise<ApiResponse<BlogPost>> {
    return this.request<BlogPost>(`/posts/admin/${id}`, {
      method: 'PUT',
      body: post,
    });
  }

  async deleteBlogPost(id: number): Promise<ApiResponse<{ message: string }>> {
    return this.request<{ message: string }>(`/posts/admin/${id}`, {
      method: 'DELETE',
    });
  }

  async publishBlogPost(id: number): Promise<ApiResponse<{ message: string }>> {
    return this.request<{ message: string }>(`/posts/admin/${id}/publish`, {
      method: 'POST',
    });
  }

  // Categories API
  async getCategories(): Promise<ApiResponse<Category[]>> {
    return this.request<Category[]>('/posts/categories');
  }

  // Admin CRUD operations for Categories
  async createCategory(
    category: Omit<Category, 'id'>
  ): Promise<ApiResponse<Category>> {
    return this.request<Category>('/posts/categories', {
      method: 'POST',
      body: category,
    });
  }

  async updateCategory(
    id: number,
    category: Partial<Category>
  ): Promise<ApiResponse<Category>> {
    return this.request<Category>(`/posts/categories/${id}`, {
      method: 'PUT',
      body: category,
    });
  }

  async deleteCategory(id: number): Promise<ApiResponse<{ message: string }>> {
    return this.request<{ message: string }>(`/posts/categories/${id}`, {
      method: 'DELETE',
    });
  }

  // Skills API
  async getSkills(): Promise<ApiResponse<Skill[]>> {
    return this.request<Skill[]>('/skills/');
  }

  async createSkill(
    skill: Omit<Skill, 'id' | 'created_at'>
  ): Promise<ApiResponse<Skill>> {
    return this.request<Skill>('/skills/', {
      method: 'POST',
      body: skill,
    });
  }

  async updateSkill(
    id: number,
    skill: Partial<Skill>
  ): Promise<ApiResponse<Skill>> {
    return this.request<Skill>(`/skills/${id}`, {
      method: 'PUT',
      body: skill,
    });
  }

  async deleteSkill(id: number): Promise<ApiResponse<{ message: string }>> {
    return this.request<{ message: string }>(`/skills/${id}`, {
      method: 'DELETE',
    });
  }

  // Education API
  async getEducation(): Promise<ApiResponse<Education[]>> {
    return this.request<Education[]>('/education/');
  }

  async createEducation(
    entry: Omit<Education, 'id' | 'created_at'>
  ): Promise<ApiResponse<Education>> {
    return this.request<Education>('/education/', {
      method: 'POST',
      body: entry,
    });
  }

  async updateEducation(
    id: number,
    entry: Partial<Education>
  ): Promise<ApiResponse<Education>> {
    return this.request<Education>(`/education/${id}`, {
      method: 'PUT',
      body: entry,
    });
  }

  async deleteEducation(id: number): Promise<ApiResponse<{ message: string }>> {
    return this.request<{ message: string }>(`/education/${id}`, {
      method: 'DELETE',
    });
  }

  // Certifications API
  async getCertifications(): Promise<ApiResponse<Certification[]>> {
    return this.request<Certification[]>('/certifications/');
  }

  async createCertification(
    entry: Omit<Certification, 'id' | 'created_at'>
  ): Promise<ApiResponse<Certification>> {
    return this.request<Certification>('/certifications/', {
      method: 'POST',
      body: entry,
    });
  }

  async updateCertification(
    id: number,
    entry: Partial<Certification>
  ): Promise<ApiResponse<Certification>> {
    return this.request<Certification>(`/certifications/${id}`, {
      method: 'PUT',
      body: entry,
    });
  }

  async deleteCertification(
    id: number
  ): Promise<ApiResponse<{ message: string }>> {
    return this.request<{ message: string }>(`/certifications/${id}`, {
      method: 'DELETE',
    });
  }

  // Site Content API (singleton)
  async getSiteContent(): Promise<ApiResponse<SiteContent>> {
    return this.request<SiteContent>('/site-content/');
  }

  async updateSiteContent(
    patch: Partial<SiteContent>
  ): Promise<ApiResponse<SiteContent>> {
    return this.request<SiteContent>('/site-content/', {
      method: 'PUT',
      body: patch,
    });
  }
}

// Create and export a singleton instance
export const apiService = new ApiService();
