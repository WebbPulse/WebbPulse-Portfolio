import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiService } from './api';

const BASE = 'https://api.example.test/api/v1';

/**
 * The route keys `terraform/apigateway.tf` flags with `require_identity_jwt`
 * under `/api/v1`, copied from `local.domain_identity_jwt_route_paths`.
 *
 * API Gateway hands authorizer claims only to a request that matches one of
 * these exactly. A path with a trailing slash falls through to the anonymous
 * `ANY /api/v1/<prefix>/{proxy+}` route and the function answers 401.
 */
const FLAGGED_ROUTE_KEYS = [
  'GET /api/v1/posts/admin',
  'POST /api/v1/posts/admin',
  'PUT /api/v1/posts/admin/{post_id}',
  'DELETE /api/v1/posts/admin/{post_id}',
  'POST /api/v1/posts/admin/{post_id}/publish',
  'POST /api/v1/posts/categories',
  'PUT /api/v1/posts/categories/{category_id}',
  'DELETE /api/v1/posts/categories/{category_id}',
  'PUT /api/v1/site-content',
  'POST /api/v1/certifications',
  'PUT /api/v1/certifications/{item_id}',
  'DELETE /api/v1/certifications/{item_id}',
  'POST /api/v1/education',
  'PUT /api/v1/education/{item_id}',
  'DELETE /api/v1/education/{item_id}',
  'POST /api/v1/experience',
  'PUT /api/v1/experience/{item_id}',
  'DELETE /api/v1/experience/{item_id}',
  'POST /api/v1/projects',
  'PUT /api/v1/projects/{item_id}',
  'DELETE /api/v1/projects/{item_id}',
  'POST /api/v1/skills',
  'PUT /api/v1/skills/{item_id}',
  'DELETE /api/v1/skills/{item_id}',
];

/** Every `ApiService` call that needs the caller's claims, invoked once. */
const AUTHENTICATED_CALLS: Record<
  string,
  (api: ApiService) => Promise<unknown>
> = {
  getAdminBlogPosts: (api) => api.getAdminBlogPosts(),
  createBlogPost: (api) =>
    api.createBlogPost({ title: 't', slug: 's', content: 'c' }),
  updateBlogPost: (api) => api.updateBlogPost(1, { title: 't' }),
  deleteBlogPost: (api) => api.deleteBlogPost(1),
  publishBlogPost: (api) => api.publishBlogPost(1),
  createCategory: (api) => api.createCategory({ name: 'n', slug: 's' }),
  updateCategory: (api) => api.updateCategory(1, { name: 'n' }),
  deleteCategory: (api) => api.deleteCategory(1),
  updateSiteContent: (api) => api.updateSiteContent({ hero_title: 'h' }),
  createCertification: (api) =>
    api.createCertification({
      name: 'n',
      issuer: 'i',
      issued_date: '2026-01-01',
      order: 0,
    }),
  updateCertification: (api) => api.updateCertification(1, { name: 'n' }),
  deleteCertification: (api) => api.deleteCertification(1),
  createEducation: (api) =>
    api.createEducation({
      degree: 'd',
      school: 's',
      location: 'l',
      period: 'p',
      start_date: '2020-01-01',
      order: 0,
    }),
  updateEducation: (api) => api.updateEducation(1, { degree: 'd' }),
  deleteEducation: (api) => api.deleteEducation(1),
  createExperience: (api) =>
    api.createExperience({
      title: 't',
      company: 'c',
      location: 'l',
      period: 'p',
      start_date: '2020-01-01',
      description: 'd',
      technologies: [],
      achievements: [],
    }),
  updateExperience: (api) => api.updateExperience(1, { title: 't' }),
  deleteExperience: (api) => api.deleteExperience(1),
  createProject: (api) =>
    api.createProject({
      title: 't',
      description: 'd',
      image: 'i',
      technologies: [],
      featured: false,
      display_order: 0,
    }),
  updateProject: (api) => api.updateProject(1, { title: 't' }),
  deleteProject: (api) => api.deleteProject(1),
  createSkill: (api) =>
    api.createSkill({
      name: 'n',
      category: 'backend',
      tier: 'core',
      order: 0,
    }),
  updateSkill: (api) => api.updateSkill(1, { name: 'n' }),
  deleteSkill: (api) => api.deleteSkill(1),
};

/** Whether `method path` matches a route key, treating `{name}` as one segment. */
function matchesRouteKey(routeKey: string, method: string, path: string) {
  const [keyMethod, keyPath] = routeKey.split(' ', 2) as [string, string];
  if (keyMethod !== method) {
    return false;
  }
  const pattern = keyPath
    .split('/')
    .map((part) => (/^\{[^}+]+\}$/.test(part) ? '[^/]+' : part))
    .join('/');
  return new RegExp(`^${pattern}$`).test(path);
}

describe('authenticated request paths', () => {
  let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;

  beforeEach(() => {
    fetchMock = vi.fn<typeof fetch>();
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        new Response('{}', {
          status: 200,
          headers: { 'content-type': 'application/json' },
        })
      )
    );
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  /** The method and path of the single request `call` made. */
  async function requestOf(
    call: (api: ApiService) => Promise<unknown>
  ): Promise<{ method: string; path: string }> {
    await call(new ApiService(BASE));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    return {
      method: (init.method ?? 'GET').toUpperCase(),
      path: new URL(url).pathname,
    };
  }

  it('covers every write method the service exposes', () => {
    const writes = Object.getOwnPropertyNames(ApiService.prototype).filter(
      (name) => /^(create|update|delete|publish)[A-Z]/.test(name)
    );
    expect(writes.length).toBeGreaterThan(0);
    expect(writes.filter((name) => !(name in AUTHENTICATED_CALLS))).toEqual([]);
  });

  it.each(Object.entries(AUTHENTICATED_CALLS))(
    '%s calls a flagged route key exactly, with no trailing slash',
    async (_name, call) => {
      const { method, path } = await requestOf(call);

      expect(path.endsWith('/')).toBe(false);
      expect(
        FLAGGED_ROUTE_KEYS.filter((key) => matchesRouteKey(key, method, path))
      ).toHaveLength(1);
    }
  );

  it('rejects a trailing slash against the flagged keys', () => {
    expect(
      FLAGGED_ROUTE_KEYS.some((key) =>
        matchesRouteKey(key, 'POST', '/api/v1/projects/')
      )
    ).toBe(false);
    expect(
      FLAGGED_ROUTE_KEYS.some((key) =>
        matchesRouteKey(key, 'PUT', '/api/v1/site-content/')
      )
    ).toBe(false);
  });
});
