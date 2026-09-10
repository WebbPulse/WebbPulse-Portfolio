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
//
// Authentication is mid migration and the mechanism is chosen by
// configuration. See `services/authMode.ts` for the two modes and
// `IDENTITY_CUTOVER` below for what the identity mode is waiting on.
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
 * The auth mechanism this bundle runs, read once at startup.
 *
 * `ConfigReader` rather than a raw `import.meta.env` read so an unrecognised
 * value fails by name at startup, next to every other configuration problem,
 * instead of quietly selecting the fallback. `assertValid` is what turns a
 * recorded issue into the throw.
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
 * The `identity` branch below is written against the real `@webbpulse/auth`
 * 0.4.0 API and compiles today. It is not switched on because the routes it
 * calls do not exist in Portfolio yet, and that is a backend milestone rather
 * than anything left undone here:
 *
 * 1. The identity function serves `POST /api/auth/login`, `/api/auth/refresh`
 *    and `/api/auth/logout`. Staging currently serves only the JWKS,
 *    the OpenID discovery document and the function's health route.
 * 2. The refresh cookie is set httpOnly, `SameSite=Lax` and `Secure`, scoped
 *    to the registrable domain. The www host and the API host share that
 *    domain, so a fetch between them is same site and Lax is enough; the
 *    standard rules out `SameSite=None`. The client already sends
 *    `credentials: 'include'` for the staging access gate, which is the same
 *    requirement for a cross origin, same site request.
 * 3. The login route takes the standard's `email` and `password` and answers
 *    `{ access_token, expires_in }`. Portfolio's current route takes
 *    `username` and answers `{ access_token, token_type }`, which is why
 *    `login` below has two shapes rather than one.
 *
 * When those are live, `VITE_AUTH_MODE=identity` is set on the environment,
 * and once every environment carries it the bearer branch,
 * `BearerTokenStore` and `services/authMode.ts` are deleted together.
 */
export const IDENTITY_CUTOVER = {
  /** Routes `AuthClient` needs that Portfolio does not serve yet. */
  requiredRoutes: [
    '/api/auth/login',
    '/api/auth/refresh',
    '/api/auth/logout',
  ] as const,
} as const;

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

  /**
   * The bearer store, in `bearer` mode only.
   *
   * Null under `identity`, where the access token lives in `AuthClient` and
   * writing it anywhere a script can read back after a reload is the thing the
   * standard exists to prevent.
   */
  private readonly tokenStore: BearerTokenStore | null;

  /** The auth client, in `identity` mode only. */
  private readonly auth: AuthClient<unknown> | null;

  constructor(baseUrl: string = API_BASE_URL, mode: AuthMode = AUTH_MODE) {
    // The client defaults to credentials: 'include', which the staging access
    // gate needs: its CloudFront signed cookies are set on the staging apex, so
    // a request from the www host to the API host only carries them when
    // credentials are included. It is also what attaches the identity refresh
    // cookie cross origin, so both modes need it. Stated explicitly so it is
    // not lost to a future default change.
    const credentials = 'include' as const;

    if (mode === 'identity') {
      this.tokenStore = null;
      // `AuthClient` builds its own client for the identity routes, which must
      // stay callable with an expired token, so it is never given a
      // `getAuthToken` pointing back at itself.
      this.auth = createAuthClient({
        baseUrl,
        clientOptions: { credentials },
      });
      this.client = this.buildClient(baseUrl, {
        credentials,
        // Passing the client as `auth` turns on the retry-once-on-401
        // pipeline: one shared refresh, one replay, and a second 401 thrown
        // rather than a third attempt.
        auth: this.auth satisfies AuthTokenProvider,
      });
      return;
    }

    // BearerTokenStore degrades to an in memory store when localStorage
    // throws, which Safari in private mode does, so reading a token cannot
    // break the application on load.
    const store = new BearerTokenStore(TOKEN_STORAGE_KEY);
    this.tokenStore = store;
    this.auth = null;
    this.client = this.buildClient(baseUrl, {
      credentials,
      // Read synchronously on every request, which is what the client
      // requires. There is no refresh route in this mode, so an expired token
      // is a 401 the user resolves by signing in again.
      getAuthToken: () => store.get(),
      // The API reissues a token in a response header after a username change.
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
      // The package logs nothing of its own, so reporting stays a decision
      // this application makes. Keeping console.error preserves what the hand
      // rolled adapter did; the hook is where a real reporter goes.
      onError: error => {
        logApiFailure(error);
      },
    });
  }

  /**
   * The auth client, when this bundle runs the identity mode.
   *
   * Exposed so `AuthProvider` from `@webbpulse/auth/react` can be given the
   * same instance the API client refreshes through, rather than a second one
   * with its own token and its own in-flight refresh.
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

  // Authentication methods
  //
  // The signatures are unchanged across both modes, so `AdminPanel` and the
  // login form do not change when the cutover happens. What changes underneath
  // is where the token lives and whether a refresh exists.

  /**
   * Signs in.
   *
   * In `identity` mode this goes through `AuthClient`, which holds the access
   * token in memory and relies on the refresh cookie the route sets. The
   * standard's login takes `email`, so the username is sent as one: the field
   * carries an email address in practice, and the identity route is the thing
   * that defines the name.
   *
   * An MFA challenge is a successful outcome of the first leg rather than an
   * error, and Portfolio has no second factor enrolled, so it is reported as a
   * failed login here rather than silently read as success. Completing a
   * challenge needs a form this application does not have; it is added with
   * the rest of the identity UI when the routes land.
   */
  async login(credentials: UserLogin): Promise<ApiResponse<Token>> {
    if (this.auth !== null) {
      const auth = this.auth;
      try {
        const outcome = await auth.login({
          email: credentials.username,
          password: credentials.password,
        });
        if (outcome.mfaRequired) {
          return {
            data: null,
            error: 'This account requires a second factor to sign in.',
          };
        }
        const token = auth.getAccessToken();
        return {
          data:
            token === null
              ? null
              : { access_token: token, token_type: 'bearer' },
          ...(token === null
            ? { error: 'Sign in did not return an access token.' }
            : {}),
        };
      } catch (error) {
        logApiFailure(error);
        return {
          data: null,
          error:
            error instanceof Error
              ? error.message
              : 'Sign in failed. Please try again.',
        };
      }
    }

    const response = await this.request<Token>('/admin/login', {
      method: 'POST',
      body: credentials,
    });

    if (response.data) {
      this.tokenStore?.set(response.data.access_token);
    }

    return response;
  }

  /**
   * Signs out.
   *
   * Stays synchronous, because every call site treats signing out as immediate
   * and none of them awaits it. In `identity` mode the backend call that
   * revokes the refresh family is started and not awaited; `AuthClient` clears
   * its in-memory token whether or not that call succeeds, so the local
   * session is gone by the time this returns either way.
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
    // Read through on every call rather than caching in a field. The previous
    // cached copy went stale whenever another tab signed in or out.
    const token = this.tokenStore?.get() ?? null;
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
