import {
  ApiError,
  createApiClient,
  createEnvelopeClient,
  getWebbPulseError,
  type ApiEnvelope,
  type AuthTokenProvider,
  type EnvelopeClient,
} from '@webbpulse/api-client';
import { ConfigReader, loadAppConfig } from '@webbpulse/config';
import { createAuthClient, type AuthClient } from '@webbpulse/auth';

import { AUTH_MODES, AUTH_MODE_ENV_KEY, type AuthMode } from './authMode';
import { BearerTokenStore } from './bearerTokenStore';

/** Key the auth token is stored under. Unchanged, so sessions survive deploy. */
const TOKEN_STORAGE_KEY = 'authToken';

const config = loadAppConfig(import.meta.env, {
  defaultApiBaseUrl:
    import.meta.env.MODE === 'production'
      ? 'https://api.webbpulse.com/api/v1'
      : 'http://localhost:8000/api/v1',
  defaultAppName: 'WebbPulse Portfolio',
});

/** Base URL of this application's API, from the resolved app config. */
export const API_BASE_URL = config.apiBaseUrl;

/**
 * The origin the identity routes hang off, derived from the API base URL.
 *
 * Identity mounts at `/api/auth` on the origin while this application's routes
 * live under `/api/v1`. Falls back to the unmodified base when it will not parse.
 */
export function identityOriginFrom(apiBaseUrl: string): string {
  try {
    return new URL(apiBaseUrl).origin;
  } catch {
    return apiBaseUrl;
  }
}

/**
 * The auth mechanism this bundle runs, read once at startup.
 *
 * Read through `ConfigReader` so an unrecognised value fails by name at startup.
 */
export const AUTH_MODE: AuthMode = (() => {
  const reader = new ConfigReader(import.meta.env);
  const mode = reader.oneOf(AUTH_MODE_ENV_KEY, AUTH_MODES, 'bearer');
  reader.assertValid();
  return mode;
})();

/**
 * What the identity cutover still needs, in one place.
 *
 * The routes are live; what remains is setting `AUTH_MODE=identity` per
 * environment, after which the bearer branch and its store are deleted.
 */
export const IDENTITY_CUTOVER = {
  /** The GitHub Environment variable that selects the mode at build time. */
  environmentVariable: 'AUTH_MODE',
  /** The value that turns the identity mode on. */
  enabledValue: 'identity',
} as const;

/**
 * Logs a failed request with the fields the backend's error envelope carries.
 *
 * `getWebbPulseError` reads the message, status and request id off the shared
 * envelope, and `errorCode` is logged only when the backend sends one.
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
  console.error('API request failed:', error);
}

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

/** Credentials posted to the sign in route. */
export interface UserLogin {
  username: string;
  password: string;
}

/** A bearer access token as the API returns it. */
export interface Token {
  access_token: string;
  token_type: string;
}

/**
 * What a sign in attempt produced.
 *
 * An MFA challenge is its own case rather than an error: it is a successful
 * first leg that carries no access token. `bearer` mode never produces it.
 */
export type LoginResult =
  | { status: 'authenticated' }
  | { status: 'mfa-required'; ticket: string }
  | { status: 'failed'; error: string };

/**
 * The envelope every call site in this application reads.
 *
 * The package's `ApiEnvelope`, so `data` is typed `T | null` as the error path
 * always returned.
 */
export type ApiResponse<T> = ApiEnvelope<T>;

/** Typed client for the portfolio API, covering both auth modes. */
export class ApiService {
  private readonly client: EnvelopeClient;

  /**
   * The bearer store, in `bearer` mode only.
   *
   * Null under `identity`, where the access token lives in `AuthClient` instead.
   */
  private readonly tokenStore: BearerTokenStore | null;

  /** The auth client, in `identity` mode only. */
  private readonly auth: AuthClient<unknown> | null;

  /** Subscribers notified when a live session ends on its own. */
  private readonly sessionEndedListeners = new Set<() => void>();

  constructor(baseUrl: string = API_BASE_URL, mode: AuthMode = AUTH_MODE) {
    const credentials = 'include' as const;

    if (mode === 'identity') {
      this.tokenStore = null;
      this.auth = createAuthClient({
        baseUrl: identityOriginFrom(baseUrl),
        clientOptions: { credentials },
        onSessionEnded: () => {
          this.notifySessionEnded();
        },
      });
      this.client = this.buildClient(baseUrl, {
        credentials,
        auth: this.auth satisfies AuthTokenProvider,
      });
      return;
    }

    const store = new BearerTokenStore(TOKEN_STORAGE_KEY);
    this.tokenStore = store;
    this.auth = null;
    this.client = this.buildClient(baseUrl, {
      credentials,
      getAuthToken: () => store.get(),
      onTokenRefresh: (token: string) => {
        store.set(token);
      },
    });
  }

  /** The one place the envelope client is constructed, for either mode. */
  private buildClient(
    baseUrl: string,
    options: {
      credentials: RequestCredentials;
      auth?: AuthTokenProvider;
      getAuthToken?: () => string | null;
      onTokenRefresh?: (token: string) => void;
    }
  ): EnvelopeClient {
    return createEnvelopeClient(createApiClient({ baseUrl, ...options }), {
      onError: error => {
        logApiFailure(error);
      },
    });
  }

  /**
   * The auth client, when this bundle runs the identity mode.
   *
   * Exposed so `AuthProvider` shares the instance the API client refreshes through.
   */
  getAuthClient(): AuthClient<unknown> | null {
    return this.auth;
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

  /**
   * Signs in.
   *
   * In `identity` mode the username is sent as the standard's `email` field. An
   * MFA challenge comes back as its own result carrying the ticket to finish with.
   */
  async login(credentials: UserLogin): Promise<LoginResult> {
    if (this.auth !== null) {
      const auth = this.auth;
      try {
        const outcome = await auth.login({
          email: credentials.username,
          password: credentials.password,
        });
        return this.readLoginOutcome(outcome);
      } catch (error) {
        return this.readLoginFailure(error);
      }
    }

    const response = await this.request<Token>('/admin/login', {
      method: 'POST',
      body: credentials,
    });

    if (response.data) {
      this.tokenStore?.set(response.data.access_token);
      return { status: 'authenticated' };
    }

    return {
      status: 'failed',
      error: response.error ?? 'Sign in failed. Please try again.',
    };
  }

  /**
   * Finishes an MFA login with a TOTP code.
   *
   * `identity` mode only; answers with a failure rather than throwing in `bearer`.
   */
  async completeTotp(input: {
    ticket: string;
    code: string;
  }): Promise<LoginResult> {
    if (this.auth === null) {
      return {
        status: 'failed',
        error: 'A second factor is not available in this mode.',
      };
    }
    try {
      return this.readLoginOutcome(await this.auth.completeTotp(input));
    } catch (error) {
      return this.readLoginFailure(error);
    }
  }

  /** Turns a package login outcome into this application's result. */
  private readLoginOutcome(outcome: {
    mfaRequired: boolean;
    ticket?: string;
  }): LoginResult {
    if (outcome.mfaRequired) {
      return {
        status: 'mfa-required',
        ticket: outcome.ticket ?? '',
      };
    }
    return { status: 'authenticated' };
  }

  /** Turns a thrown login error into a rendered sentence. */
  private readLoginFailure(error: unknown): LoginResult {
    logApiFailure(error);
    return {
      status: 'failed',
      error:
        error instanceof ApiError
          ? getWebbPulseError(error).message
          : 'Sign in failed. Please try again.',
    };
  }

  /**
   * The auth client, for the identity pages that call it directly.
   *
   * Those routes answer discriminated outcomes rather than this service's envelope,
   * so the pages get the client itself. Null in `bearer` mode.
   */
  getIdentityClient(): AuthClient<unknown> | null {
    return this.auth;
  }

  /**
   * Registers a callback for a session that ended without the user asking.
   * Returns the unsubscribe function. Never fires in `bearer` mode.
   */
  onSessionEnded(listener: () => void): () => void {
    this.sessionEndedListeners.add(listener);
    return () => {
      this.sessionEndedListeners.delete(listener);
    };
  }

  /** Fans a session-ended event out to every subscriber. */
  private notifySessionEnded(): void {
    for (const listener of [...this.sessionEndedListeners]) {
      listener();
    }
  }

  /**
   * Spends the refresh cookie on page load to restore the in-memory token.
   * Resolves to whether a session came back; false rather than throwing when
   * there is no cookie. In `bearer` mode reports the stored token instead.
   */
  async restoreSession(): Promise<boolean> {
    if (this.auth === null) {
      return this.isAuthenticated();
    }
    try {
      await this.auth.initialize();
    } catch {
      return false;
    }
    return this.isAuthenticated();
  }

  /**
   * Signs out.
   *
   * Synchronous: the revoke call is started and not awaited, and the in-memory
   * token is cleared either way.
   */
  logout(): void {
    if (this.auth !== null) {
      void this.auth.logout().catch(logApiFailure);
      return;
    }
    this.tokenStore?.clear();
  }

  isAuthenticated(): boolean {
    if (this.auth !== null) {
      return this.auth.getState().status === 'authenticated';
    }
    const token = this.tokenStore?.get() ?? null;
    return token !== null && token !== '';
  }

  async getProjects(
    featuredOnly: boolean = false
  ): Promise<ApiResponse<Project[]>> {
    return this.client.get<Project[]>('/projects/', {
      ...(featuredOnly ? { query: { featured_only: true } } : {}),
    });
  }

  async getProject(id: number): Promise<ApiResponse<Project>> {
    return this.request<Project>(`/projects/${id}`);
  }

  async getExperience(): Promise<ApiResponse<Experience[]>> {
    return this.request<Experience[]>('/experience/');
  }

  async getExperienceEntry(id: number): Promise<ApiResponse<Experience>> {
    return this.request<Experience>(`/experience/${id}`);
  }

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

  async getCategories(): Promise<ApiResponse<Category[]>> {
    return this.request<Category[]>('/posts/categories');
  }

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

/** Shared ApiService instance used across the application. */
export const apiService = new ApiService();
