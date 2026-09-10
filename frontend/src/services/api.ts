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
 * The origin the identity routes hang off, derived from the application's API
 * base URL.
 *
 * These are two different mount points on one host and the difference matters.
 * The application's own routes live under `/api/v1`, which is what
 * `API_BASE_URL` carries. Identity mounts at the issuer's path, `/api/auth`,
 * directly on the origin: the backend's `composition/identity.py` records that
 * the issuer is `https://<api host>/api/auth` and that every route, the
 * discovery document included, answers under it.
 *
 * `AuthClient`'s paths are absolute (`/api/auth/login` and the rest) and
 * `joinUrl` in `@webbpulse/api-client` concatenates rather than resolving, so
 * handing it `API_BASE_URL` would request `/api/v1/api/auth/login` and every
 * identity call would 404. Stripping back to the origin is what makes the
 * package's own defaults correct, which is why no path overrides are passed.
 *
 * Falls back to the unmodified base when the value will not parse, which keeps
 * a malformed configuration a visible failure at the request rather than a
 * throw at module load.
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
 * The routes `AuthClient` calls are live on staging as of M3: the identity
 * function serves `/api/auth/login`, `/logout`, `/logout-all`, `/refresh`,
 * `/password`, `/reset`, `/reset/confirm`, `/verify-email` and
 * `/verify-email/confirm` under the issuer `https://api.staging.webbpulse.com/api/auth`,
 * alongside the JWKS and the discovery document. Registration is served but
 * disabled for Portfolio, which is a single operator site.
 *
 * What remains is a deployment decision rather than code. `VITE_AUTH_MODE` is
 * unset in every environment, so every bundle still runs `bearer`. Setting
 * `AUTH_MODE=identity` on the staging GitHub Environment switches that
 * environment over; production follows once staging has run on it. When every
 * environment carries it, the bearer branch, `BearerTokenStore` and
 * `services/authMode.ts` are deleted together.
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
 * What a sign in attempt produced.
 *
 * A third case beside "signed in" and "failed", because the identity standard
 * makes an MFA challenge a *successful* outcome of the first leg that simply
 * carries no access token (2.6). Modelling it as an error, which this service
 * did before the second factor UI existed, forced the panel to read a sentence
 * out of `error` to decide what to render next.
 *
 * `bearer` mode never produces `mfaRequired`, so the panel's handling of it is
 * dead code there rather than a branch that needs a second implementation.
 */
export type LoginResult =
  | { status: 'authenticated' }
  | { status: 'mfa-required'; ticket: string }
  | { status: 'failed'; error: string };

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
        // The origin rather than `baseUrl`: identity mounts at `/api/auth` on
        // the host, not under this application's `/api/v1`. See
        // `identityOriginFrom`.
        baseUrl: identityOriginFrom(baseUrl),
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
   * An MFA challenge comes back as its own result rather than as an error. It
   * is a successful outcome of the first leg that carries no access token
   * (2.6), and the caller needs the ticket to finish the login, which an
   * `error` string cannot carry. `bearer` mode never produces it.
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
   * `identity` mode only, because only `AuthClient` can hold the ticket that
   * `login` handed back. Calling it in `bearer` mode is a programming error
   * rather than a user-visible state, so it answers with a failure rather than
   * throwing into a form's submit handler.
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
   * The two link pages and the forgot password affordance call four routes
   * that have nothing to do with a session: they are anonymous, they take an
   * email or a token in the body, and each answers with a discriminated
   * outcome rather than the `{ data, error }` envelope the rest of this
   * service converts to. Re-wrapping them here would flatten four distinct
   * reasons into one string, which is the distinction those pages exist to
   * render, so they get the client itself.
   *
   * Null in `bearer` mode, which is what gates the identity-only UI.
   */
  getIdentityClient(): AuthClient<unknown> | null {
    return this.auth;
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
