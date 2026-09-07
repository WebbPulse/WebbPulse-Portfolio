// API service for communicating with the backend
// Detect environment and set appropriate API base URL
const getApiBaseUrl = (): string => {
  // Check if we have an explicit API URL set
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }

  // Check the Vite mode to determine which backend to use
  const mode = import.meta.env.MODE;

  if (mode === 'production') {
    // Use production backend for production mode
    return 'https://api.webbpulse.com/api/v1';
  } else {
    // Use local backend for development mode (default)
    return 'http://localhost:8000/api/v1';
  }
};

const API_BASE_URL = getApiBaseUrl();

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
  excerpt?: string;
  read_time?: string;
  published_at?: string;
  created_at: string;
  updated_at?: string;
  category_id?: number;
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

export interface ApiResponse<T> {
  data: T;
  error?: string;
}

class ApiService {
  private baseUrl: string;
  private authToken: string | null = null;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
    // Try to load token from localStorage on initialization
    this.authToken = localStorage.getItem('authToken');
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    try {
      const url = `${this.baseUrl}${endpoint}`;
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };

      // Add authorization header if token exists
      if (this.authToken) {
        headers['Authorization'] = `Bearer ${this.authToken}`;
      }

      // Merge with any additional headers from options
      if (options.headers) {
        Object.assign(headers, options.headers);
      }

      // credentials: 'include' so the browser attaches cookies scoped to the
      // domain the API is served from. Production does not use cookies, but the
      // staging access gate does: its CloudFront signed cookies are set on the
      // staging apex, so a same-site request from the www host to the API host
      // carries them and the API's authorizer accepts the call.
      const response = await fetch(url, {
        ...options,
        headers,
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return { data };
    } catch (error) {
      console.error('API request failed:', error);
      return {
        data: null as T,
        error:
          error instanceof Error ? error.message : 'Unknown error occurred',
      };
    }
  }

  // Authentication methods
  async login(credentials: UserLogin): Promise<ApiResponse<Token>> {
    const response = await this.request<Token>('/admin/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    });

    if (response.data) {
      this.authToken = response.data.access_token;
      localStorage.setItem('authToken', this.authToken);
    }

    return response;
  }

  logout(): void {
    this.authToken = null;
    localStorage.removeItem('authToken');
  }

  isAuthenticated(): boolean {
    return !!this.authToken;
  }

  // Projects API
  async getProjects(
    featuredOnly: boolean = false
  ): Promise<ApiResponse<Project[]>> {
    const params = featuredOnly ? '?featured_only=true' : '';
    return this.request<Project[]>(`/projects${params}/`);
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
      body: JSON.stringify(project),
    });
  }

  async updateProject(
    id: number,
    project: Partial<Project>
  ): Promise<ApiResponse<Project>> {
    return this.request<Project>(`/projects/${id}`, {
      method: 'PUT',
      body: JSON.stringify(project),
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
      body: JSON.stringify(experience),
    });
  }

  async updateExperience(
    id: number,
    experience: Partial<Experience>
  ): Promise<ApiResponse<Experience>> {
    return this.request<Experience>(`/experience/${id}`, {
      method: 'PUT',
      body: JSON.stringify(experience),
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
      body: JSON.stringify(post),
    });
  }

  async updateBlogPost(
    id: number,
    post: Partial<BlogPost>
  ): Promise<ApiResponse<BlogPost>> {
    return this.request<BlogPost>(`/posts/admin/${id}`, {
      method: 'PUT',
      body: JSON.stringify(post),
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
      body: JSON.stringify(category),
    });
  }

  async updateCategory(
    id: number,
    category: Partial<Category>
  ): Promise<ApiResponse<Category>> {
    return this.request<Category>(`/posts/categories/${id}`, {
      method: 'PUT',
      body: JSON.stringify(category),
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
      body: JSON.stringify(skill),
    });
  }

  async updateSkill(
    id: number,
    skill: Partial<Skill>
  ): Promise<ApiResponse<Skill>> {
    return this.request<Skill>(`/skills/${id}`, {
      method: 'PUT',
      body: JSON.stringify(skill),
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
      body: JSON.stringify(entry),
    });
  }

  async updateEducation(
    id: number,
    entry: Partial<Education>
  ): Promise<ApiResponse<Education>> {
    return this.request<Education>(`/education/${id}`, {
      method: 'PUT',
      body: JSON.stringify(entry),
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
      body: JSON.stringify(entry),
    });
  }

  async updateCertification(
    id: number,
    entry: Partial<Certification>
  ): Promise<ApiResponse<Certification>> {
    return this.request<Certification>(`/certifications/${id}`, {
      method: 'PUT',
      body: JSON.stringify(entry),
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
      body: JSON.stringify(patch),
    });
  }
}

// Create and export a singleton instance
export const apiService = new ApiService();
