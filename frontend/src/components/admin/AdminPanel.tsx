import React, { useState, useEffect } from 'react';
import { Button } from '../common';
import {
  describeOAuthCallbackError,
  readOAuthCallback,
  stripOAuthParams,
} from '@webbpulse/auth';
import type { PasskeySignInOutcome } from '@webbpulse/auth';
import {
  API_BASE_URL,
  apiService,
  identityOriginFrom,
} from '../../services/api';
import { useOAuthProviders } from '../../hooks/useOAuthProviders';
import { LoginForm } from './LoginForm';
import { TotpForm } from './TotpForm';
import { ProjectForm } from './ProjectForm';
import { ExperienceForm } from './ExperienceForm';
import { BlogPostForm } from './BlogPostForm';
import { CategoryForm } from './CategoryForm';
import { SkillForm } from './SkillForm';
import { EducationForm } from './EducationForm';
import { CertificationForm } from './CertificationForm';
import { SiteContentForm } from './SiteContentForm';
import { SecuritySection } from './SecuritySection';
import type {
  AdminPanelProps,
  AdminTab,
  Project,
  Experience,
  BlogPost,
  Category,
  Skill,
  Education,
  Certification,
  ProjectFormData,
  ExperienceFormData,
  BlogPostFormData,
  CategoryFormData,
  SkillFormData,
  EducationFormData,
  CertificationFormData,
  SiteContentFormData,
} from './types';

const EMPTY_PROJECT: ProjectFormData = {
  title: '',
  description: '',
  image: '',
  technologies: [],
  github_url: '',
  live_url: '',
  featured: false,
  display_order: 0,
};
const EMPTY_EXPERIENCE: ExperienceFormData = {
  title: '',
  company: '',
  location: '',
  period: '',
  start_date: '',
  end_date: '',
  description: '',
  technologies: [],
  achievements: [],
};
const EMPTY_BLOG: BlogPostFormData = {
  title: '',
  slug: '',
  content: '',
  excerpt: '',
  read_time: '',
  category_id: undefined,
  published_at: undefined,
};
const EMPTY_CATEGORY: CategoryFormData = {
  name: '',
  slug: '',
  description: '',
};
const EMPTY_SKILL: SkillFormData = {
  name: '',
  category: 'frontend',
  tier: 'working',
  icon: '',
  order: 0,
};
const EMPTY_EDUCATION: EducationFormData = {
  degree: '',
  school: '',
  location: '',
  period: '',
  start_date: '',
  end_date: '',
  description: '',
  order: 0,
};
const EMPTY_CERTIFICATION: CertificationFormData = {
  name: '',
  issuer: '',
  issued_date: '',
  credential_url: '',
  order: 0,
};
const EMPTY_SITE_CONTENT: SiteContentFormData = {
  hero_title: '',
  hero_subtitle: '',
  hero_description: '',
  about_paragraphs: [],
  about_values: [],
  profile_image_url: '',
  resume_url: '',
  email: '',
  github_url: '',
  linkedin_url: '',
  footer_tagline: '',
  project_sort_mode: 'manual',
};

const TABS: { id: AdminTab; label: string }[] = [
  { id: 'site-content', label: 'Site Content' },
  { id: 'projects', label: 'Projects' },
  { id: 'experience', label: 'Experience' },
  { id: 'skills', label: 'Skills' },
  { id: 'education', label: 'Education' },
  { id: 'certifications', label: 'Certifications' },
  { id: 'blog', label: 'Blog Posts' },
  { id: 'categories', label: 'Categories' },
  { id: 'security', label: 'Security' },
];

export const AdminPanel: React.FC<AdminPanelProps> = ({ className = '' }) => {
  const [activeTab, setActiveTab] = useState<AdminTab>('site-content');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  /**
   * The MFA ticket from a first login leg that asked for a second factor.
   *
   * Non-null is exactly the condition for showing the code step, so there is
   * no separate boolean that could disagree with it. Identity mode only.
   */
  const [mfaTicket, setMfaTicket] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * The identity client, which is null in bearer mode.
   *
   * Null is what gates the Security tab: the five MFA routes are identity's,
   * and the bearer login route has no second factor to manage. Read on every
   * render rather than held in state because it is fixed for the life of the
   * bundle, chosen by `VITE_AUTH_MODE` at build time.
   */
  const identityClient = apiService.getIdentityClient();

  /**
   * The providers this deployment configured, probed once per page load.
   *
   * Passed to the Security tab so the "Connect ..." buttons appear only for
   * providers that exist. The list of what is already linked comes from the
   * route and is a separate question. See `services/oauthAvailability.ts`.
   */
  const oauthProviders = useOAuthProviders(
    identityClient,
    identityOriginFrom(API_BASE_URL)
  );

  // Projects
  const [projects, setProjects] = useState<Project[]>([]);
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [projectForm, setProjectForm] =
    useState<ProjectFormData>(EMPTY_PROJECT);

  // Experience
  const [experience, setExperience] = useState<Experience[]>([]);
  const [showExperienceForm, setShowExperienceForm] = useState(false);
  const [editingExperience, setEditingExperience] = useState<Experience | null>(
    null
  );
  const [experienceForm, setExperienceForm] =
    useState<ExperienceFormData>(EMPTY_EXPERIENCE);

  // Blog
  const [blogPosts, setBlogPosts] = useState<BlogPost[]>([]);
  const [showBlogPostForm, setShowBlogPostForm] = useState(false);
  const [editingPost, setEditingPost] = useState<BlogPost | null>(null);
  const [blogPostForm, setBlogPostForm] =
    useState<BlogPostFormData>(EMPTY_BLOG);

  // Categories
  const [categories, setCategories] = useState<Category[]>([]);
  const [showCategoryForm, setShowCategoryForm] = useState(false);
  const [editingCategory, setEditingCategory] = useState<Category | null>(null);
  const [categoryForm, setCategoryForm] =
    useState<CategoryFormData>(EMPTY_CATEGORY);

  // Skills
  const [skills, setSkills] = useState<Skill[]>([]);
  const [showSkillForm, setShowSkillForm] = useState(false);
  const [editingSkill, setEditingSkill] = useState<Skill | null>(null);
  const [skillForm, setSkillForm] = useState<SkillFormData>(EMPTY_SKILL);

  // Education
  const [education, setEducation] = useState<Education[]>([]);
  const [showEducationForm, setShowEducationForm] = useState(false);
  const [editingEducation, setEditingEducation] = useState<Education | null>(
    null
  );
  const [educationForm, setEducationForm] =
    useState<EducationFormData>(EMPTY_EDUCATION);

  // Certifications
  const [certifications, setCertifications] = useState<Certification[]>([]);
  const [showCertForm, setShowCertForm] = useState(false);
  const [editingCert, setEditingCert] = useState<Certification | null>(null);
  const [certForm, setCertForm] =
    useState<CertificationFormData>(EMPTY_CERTIFICATION);

  // Site Content
  const [siteContentForm, setSiteContentForm] =
    useState<SiteContentFormData>(EMPTY_SITE_CONTENT);

  /**
   * Bumped whenever a link callback lands, to make the Security tab reload.
   *
   * `ConnectedAccounts` loads its own list on mount and there is no route that
   * pushes at it, so a `?oauth_linked=1` return has to tell it to look again.
   * A counter through `key` remounts the component, which is the smallest
   * thing that reliably re-runs the load without lifting the whole list into
   * this file.
   */
  const [linksEpoch, setLinksEpoch] = useState(0);

  /**
   * Reads whatever the OAuth callback left in the address bar.
   *
   * Exactly one of four parameters is present, and `readOAuthCallback` narrows
   * them with a fixed precedence: an error outranks a ticket, which outranks a
   * link, which outranks a sign-in. That order matters because a `return_to`
   * carrying a stale `?oauth=1` of its own must not let a successful-looking
   * parameter mask a live refusal.
   *
   * The parameters are stripped immediately, before any await. The MFA ticket
   * is a live single-use bearer value and leaving it in the address bar leaves
   * it in the browser history and in the `Referer` of the next navigation. The
   * strip also stops a reload re-running this against a callback that was
   * already handled.
   *
   * Runs once, on mount, and only in identity mode: bearer mode has no OAuth
   * routes and nothing can have redirected here from one.
   */
  useEffect(() => {
    if (identityClient === null) {
      if (apiService.isAuthenticated()) setIsAuthenticated(true);
      return;
    }

    const result = readOAuthCallback(window.location.href);
    if (result !== null) {
      window.history.replaceState(
        null,
        '',
        stripOAuthParams(window.location.href)
      );
    }

    switch (result?.kind) {
      case 'signed-in':
        // The refresh cookie is already set. `initialize` spends it and puts
        // the access token in memory, which is the same thing a reload does.
        setLoading(true);
        void identityClient
          .initialize()
          .then(() => {
            setIsAuthenticated(apiService.isAuthenticated());
          })
          .catch(() => {
            setError('That sign-in could not be completed. Try again.');
          })
          .finally(() => {
            setLoading(false);
          });
        return;
      case 'mfa-required':
        // The same second leg the password path reaches, and the same screen.
        // The ticket is posted to the same route by `completeTotp`.
        setMfaTicket(result.ticket);
        return;
      case 'linked':
        setIsAuthenticated(apiService.isAuthenticated());
        setLinksEpoch(epoch => epoch + 1);
        return;
      case 'error':
        setError(describeOAuthCallbackError(result));
        setIsAuthenticated(apiService.isAuthenticated());
        return;
      default:
        setIsAuthenticated(apiService.isAuthenticated());
    }
    // Runs once. `identityClient` is fixed for the life of the bundle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    void loadProjects();
    void loadExperience();
    void loadBlogPosts();
    void loadCategories();
    void loadSkills();
    void loadEducation();
    void loadCertifications();
    void loadSiteContent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  const handleApiError = (label: string, msg: string) =>
    setError(`Failed to ${label}: ${msg}`);

  // Loaders
  const loadProjects = async () => {
    const r = await apiService.getProjects();
    if (r.error) handleApiError('load projects', r.error);
    else setProjects(r.data || []);
  };
  const loadExperience = async () => {
    const r = await apiService.getExperience();
    if (r.error) handleApiError('load experience', r.error);
    else setExperience(r.data || []);
  };
  const loadBlogPosts = async () => {
    const r = await apiService.getAdminBlogPosts();
    if (r.error) handleApiError('load blog posts', r.error);
    else setBlogPosts(r.data || []);
  };
  const loadCategories = async () => {
    const r = await apiService.getCategories();
    if (r.error) handleApiError('load categories', r.error);
    else setCategories(r.data || []);
  };
  const loadSkills = async () => {
    const r = await apiService.getSkills();
    if (r.error) handleApiError('load skills', r.error);
    else setSkills(r.data || []);
  };
  const loadEducation = async () => {
    const r = await apiService.getEducation();
    if (r.error) handleApiError('load education', r.error);
    else setEducation(r.data || []);
  };
  const loadCertifications = async () => {
    const r = await apiService.getCertifications();
    if (r.error) handleApiError('load certifications', r.error);
    else setCertifications(r.data || []);
  };
  const loadSiteContent = async () => {
    const r = await apiService.getSiteContent();
    if (r.error) {
      handleApiError('load site content', r.error);
      return;
    }
    if (r.data) {
      setSiteContentForm({
        hero_title: r.data.hero_title || '',
        hero_subtitle: r.data.hero_subtitle || '',
        hero_description: r.data.hero_description || '',
        about_paragraphs: r.data.about_paragraphs || [],
        about_values: (r.data.about_values || []).map(v => ({
          title: v.title,
          description: v.description,
          icon: v.icon || '',
        })),
        profile_image_url: r.data.profile_image_url || '',
        resume_url: r.data.resume_url || '',
        email: r.data.email || '',
        github_url: r.data.github_url || '',
        linkedin_url: r.data.linkedin_url || '',
        footer_tagline: r.data.footer_tagline || '',
        project_sort_mode: r.data.project_sort_mode || 'manual',
      });
    }
  };

  const handleLogin = async (username: string, password: string) => {
    setLoading(true);
    setError(null);
    try {
      const r = await apiService.login({ username, password });
      if (r.status === 'authenticated') setIsAuthenticated(true);
      else if (r.status === 'mfa-required') setMfaTicket(r.ticket);
      else setError(r.error);
    } catch {
      setError('Login failed');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Settles a sign-in that came from a passkey rather than a password.
   *
   * The same two landings the password path has, reached by the same states,
   * which is the point: `LoginForm` runs the ceremony because the ceremony
   * needs a user gesture, and hands back the outcome because only this file
   * owns the session and the MFA ticket.
   *
   * A user-verified passkey is two factors in one gesture and arrives already
   * signed in. One from an authenticator that did not verify the user, on an
   * account with TOTP, arrives with a ticket for the same code step and the
   * same route the password path uses.
   *
   * Refusals never reach here. `LoginForm` renders them, and swallows a
   * dismissed prompt entirely.
   */
  const handlePasskeySignIn = (outcome: PasskeySignInOutcome) => {
    if (!outcome.ok) return;
    if (outcome.kind === 'mfa-required') {
      setMfaTicket(outcome.ticket);
      return;
    }
    setError(null);
    setIsAuthenticated(apiService.isAuthenticated());
  };

  /**
   * Finishes a login that asked for a second factor.
   *
   * Clearing the ticket on success matters as much as setting the session:
   * the ticket is single use, so leaving it in state would show the code step
   * again on the next sign out with a value the server has already spent.
   */
  const handleTotp = async (code: string) => {
    if (mfaTicket === null) return;
    setLoading(true);
    setError(null);
    try {
      const r = await apiService.completeTotp({ ticket: mfaTicket, code });
      if (r.status === 'authenticated') {
        setMfaTicket(null);
        setIsAuthenticated(true);
      } else if (r.status === 'mfa-required') {
        setMfaTicket(r.ticket);
      } else {
        setError(r.error);
      }
    } catch {
      setError('Login failed');
    } finally {
      setLoading(false);
    }
  };

  // Project CRUD
  const handleProjectSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const r = editingProject
      ? await apiService.updateProject(editingProject.id, projectForm)
      : await apiService.createProject(projectForm);
    if (r.error) handleApiError('save project', r.error);
    else {
      await loadProjects();
      setShowProjectForm(false);
      setEditingProject(null);
      setProjectForm(EMPTY_PROJECT);
    }
    setLoading(false);
  };
  const handleProjectEdit = (p: Project) => {
    setEditingProject(p);
    setProjectForm({
      title: p.title,
      description: p.description,
      image: p.image || '',
      technologies: p.technologies,
      github_url: p.github_url || '',
      live_url: p.live_url || '',
      featured: p.featured,
      display_order: p.display_order ?? 0,
    });
    setShowProjectForm(true);
  };
  const handleProjectDelete = async (id: number) => {
    if (!confirm('Delete this project?')) return;
    setLoading(true);
    const r = await apiService.deleteProject(id);
    if (r.error) handleApiError('delete project', r.error);
    else await loadProjects();
    setLoading(false);
  };

  // Experience CRUD
  const handleExperienceSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const r = editingExperience
      ? await apiService.updateExperience(editingExperience.id, experienceForm)
      : await apiService.createExperience(experienceForm);
    if (r.error) handleApiError('save experience', r.error);
    else {
      await loadExperience();
      setShowExperienceForm(false);
      setEditingExperience(null);
      setExperienceForm(EMPTY_EXPERIENCE);
    }
    setLoading(false);
  };
  const handleExperienceEdit = (exp: Experience) => {
    setEditingExperience(exp);
    setExperienceForm({
      title: exp.title,
      company: exp.company,
      location: exp.location,
      period: exp.period,
      start_date: exp.start_date,
      end_date: exp.end_date || '',
      description: exp.description,
      technologies: exp.technologies,
      achievements: exp.achievements,
    });
    setShowExperienceForm(true);
  };
  const handleExperienceDelete = async (id: number) => {
    if (!confirm('Delete this experience entry?')) return;
    setLoading(true);
    const r = await apiService.deleteExperience(id);
    if (r.error) handleApiError('delete experience', r.error);
    else await loadExperience();
    setLoading(false);
  };

  // Blog CRUD
  const handleBlogPostSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const r = editingPost
      ? await apiService.updateBlogPost(editingPost.id, blogPostForm)
      : await apiService.createBlogPost(blogPostForm);
    if (r.error) handleApiError('save blog post', r.error);
    else {
      await loadBlogPosts();
      setShowBlogPostForm(false);
      setEditingPost(null);
      setBlogPostForm(EMPTY_BLOG);
    }
    setLoading(false);
  };
  const handleBlogPostEdit = (post: BlogPost) => {
    setEditingPost(post);
    setBlogPostForm({
      title: post.title,
      slug: post.slug,
      content: post.content,
      excerpt: post.excerpt || '',
      read_time: post.read_time || '',
      category_id: post.category_id || undefined,
      published_at: post.published_at || undefined,
    });
    setShowBlogPostForm(true);
  };
  const handleBlogPostDelete = async (id: number) => {
    if (!confirm('Delete this blog post?')) return;
    setLoading(true);
    const r = await apiService.deleteBlogPost(id);
    if (r.error) handleApiError('delete blog post', r.error);
    else await loadBlogPosts();
    setLoading(false);
  };
  const handleBlogPostPublish = async (id: number) => {
    setLoading(true);
    const r = await apiService.publishBlogPost(id);
    if (r.error) handleApiError('publish blog post', r.error);
    else await loadBlogPosts();
    setLoading(false);
  };

  // Category CRUD
  const handleCategorySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const r = editingCategory
      ? await apiService.updateCategory(editingCategory.id, categoryForm)
      : await apiService.createCategory(categoryForm);
    if (r.error) handleApiError('save category', r.error);
    else {
      await loadCategories();
      setShowCategoryForm(false);
      setEditingCategory(null);
      setCategoryForm(EMPTY_CATEGORY);
    }
    setLoading(false);
  };
  const handleCategoryEdit = (c: Category) => {
    setEditingCategory(c);
    setCategoryForm({
      name: c.name,
      slug: c.slug,
      description: c.description || '',
    });
    setShowCategoryForm(true);
  };
  const handleCategoryDelete = async (id: number) => {
    if (!confirm('Delete this category?')) return;
    setLoading(true);
    const r = await apiService.deleteCategory(id);
    if (r.error) handleApiError('delete category', r.error);
    else await loadCategories();
    setLoading(false);
  };

  // Skill CRUD
  const handleSkillSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const r = editingSkill
      ? await apiService.updateSkill(editingSkill.id, skillForm)
      : await apiService.createSkill(skillForm);
    if (r.error) handleApiError('save skill', r.error);
    else {
      await loadSkills();
      setShowSkillForm(false);
      setEditingSkill(null);
      setSkillForm(EMPTY_SKILL);
    }
    setLoading(false);
  };
  const handleSkillEdit = (s: Skill) => {
    setEditingSkill(s);
    setSkillForm({
      name: s.name,
      category: s.category,
      tier: s.tier,
      icon: s.icon || '',
      order: s.order,
    });
    setShowSkillForm(true);
  };
  const handleSkillDelete = async (id: number) => {
    if (!confirm('Delete this skill?')) return;
    setLoading(true);
    const r = await apiService.deleteSkill(id);
    if (r.error) handleApiError('delete skill', r.error);
    else await loadSkills();
    setLoading(false);
  };

  // Education CRUD
  const handleEducationSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    // Convert empty strings to nulls. These fields are `string | null` on the
    // wire, and null is what clears them; omitting the key would leave the
    // stored value untouched.
    const payload = {
      ...educationForm,
      end_date: educationForm.end_date || null,
      description: educationForm.description || null,
    };
    const r = editingEducation
      ? await apiService.updateEducation(editingEducation.id, payload)
      : await apiService.createEducation(payload);
    if (r.error) handleApiError('save education', r.error);
    else {
      await loadEducation();
      setShowEducationForm(false);
      setEditingEducation(null);
      setEducationForm(EMPTY_EDUCATION);
    }
    setLoading(false);
  };
  const handleEducationEdit = (ed: Education) => {
    setEditingEducation(ed);
    setEducationForm({
      degree: ed.degree,
      school: ed.school,
      location: ed.location,
      period: ed.period,
      start_date: ed.start_date,
      end_date: ed.end_date || '',
      description: ed.description || '',
      order: ed.order,
    });
    setShowEducationForm(true);
  };
  const handleEducationDelete = async (id: number) => {
    if (!confirm('Delete this education entry?')) return;
    setLoading(true);
    const r = await apiService.deleteEducation(id);
    if (r.error) handleApiError('delete education', r.error);
    else await loadEducation();
    setLoading(false);
  };

  // Certification CRUD
  const handleCertSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const payload = {
      ...certForm,
      credential_url: certForm.credential_url || null,
    };
    const r = editingCert
      ? await apiService.updateCertification(editingCert.id, payload)
      : await apiService.createCertification(payload);
    if (r.error) handleApiError('save certification', r.error);
    else {
      await loadCertifications();
      setShowCertForm(false);
      setEditingCert(null);
      setCertForm(EMPTY_CERTIFICATION);
    }
    setLoading(false);
  };
  const handleCertEdit = (c: Certification) => {
    setEditingCert(c);
    setCertForm({
      name: c.name,
      issuer: c.issuer,
      issued_date: c.issued_date,
      credential_url: c.credential_url || '',
      order: c.order,
    });
    setShowCertForm(true);
  };
  const handleCertDelete = async (id: number) => {
    if (!confirm('Delete this certification?')) return;
    setLoading(true);
    const r = await apiService.deleteCertification(id);
    if (r.error) handleApiError('delete certification', r.error);
    else await loadCertifications();
    setLoading(false);
  };

  // Site Content
  const handleSiteContentSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const r = await apiService.updateSiteContent(siteContentForm);
    if (r.error) handleApiError('save site content', r.error);
    else await loadSiteContent();
    setLoading(false);
  };

  if (!isAuthenticated) {
    if (mfaTicket !== null) {
      return (
        <TotpForm
          onSubmit={handleTotp}
          onCancel={() => {
            setMfaTicket(null);
            setError(null);
          }}
          loading={loading}
          error={error}
          className={className}
        />
      );
    }
    return (
      <LoginForm
        onLogin={handleLogin}
        onPasskeySignIn={handlePasskeySignIn}
        loading={loading}
        error={error}
        className={className}
      />
    );
  }

  return (
    <div
      className={`min-h-screen bg-gray-50 dark:bg-gray-900 py-12 ${className}`}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                Admin Panel
              </h1>
              <div className="flex gap-3">
                <Button
                  variant="outline"
                  onClick={() => (window.location.href = '/')}
                  size="sm"
                >
                  Back to Main Page
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    apiService.logout();
                    setIsAuthenticated(false);
                  }}
                  size="sm"
                >
                  Logout
                </Button>
              </div>
            </div>
          </div>

          <div className="px-6 py-3 border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
            <nav className="flex gap-1 min-w-max">
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`py-2 px-3 rounded-md text-sm font-medium whitespace-nowrap transition-colors ${
                    activeTab === tab.id
                      ? 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300'
                      : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>

          {error && (
            <div className="px-6 py-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 flex items-center justify-between">
              <span>{error}</span>
              <button
                onClick={() => setError(null)}
                className="text-red-500 hover:text-red-700 ml-4"
                aria-label="Dismiss error"
              >
                ×
              </button>
            </div>
          )}

          <div className="p-6">
            {/* Site Content */}
            {activeTab === 'site-content' && (
              <div>
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-6">
                  Site Content
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
                  These values appear in the Hero, About, Contact, and Footer
                  sections of the public site.
                </p>
                <SiteContentForm
                  form={siteContentForm}
                  setForm={setSiteContentForm}
                  onSubmit={handleSiteContentSubmit}
                  loading={loading}
                />
              </div>
            )}

            {/* Projects */}
            {activeTab === 'projects' && (
              <div>
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                    Manage Projects
                  </h2>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setShowProjectForm(true);
                      setEditingProject(null);
                      setProjectForm(EMPTY_PROJECT);
                    }}
                    disabled={loading}
                  >
                    Add New Project
                  </Button>
                </div>
                {showProjectForm && (
                  <ProjectForm
                    form={projectForm}
                    setForm={setProjectForm}
                    onSubmit={handleProjectSubmit}
                    onCancel={() => {
                      setShowProjectForm(false);
                      setEditingProject(null);
                      setProjectForm(EMPTY_PROJECT);
                    }}
                    editingProject={editingProject}
                    loading={loading}
                  />
                )}
                <div className="space-y-4">
                  {projects.map(project => (
                    <div
                      key={project.id}
                      className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                            {project.title}
                            {project.featured && (
                              <span className="ml-2 px-2 py-1 bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200 text-xs rounded-full">
                                Featured
                              </span>
                            )}
                          </h3>
                          <p className="text-gray-600 dark:text-gray-300 mt-1">
                            {project.description}
                          </p>
                          <div className="flex flex-wrap gap-1 mt-2">
                            {project.technologies.map((tech, i) => (
                              <span
                                key={i}
                                className="px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full text-xs"
                              >
                                {tech}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div className="flex gap-2 ml-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleProjectEdit(project)}
                            disabled={loading}
                          >
                            Edit
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void handleProjectDelete(project.id)}
                            disabled={loading}
                            className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                          >
                            Delete
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Experience */}
            {activeTab === 'experience' && (
              <div>
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                    Manage Experience
                  </h2>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setShowExperienceForm(true);
                      setEditingExperience(null);
                      setExperienceForm(EMPTY_EXPERIENCE);
                    }}
                    disabled={loading}
                  >
                    Add New Experience
                  </Button>
                </div>
                {showExperienceForm && (
                  <ExperienceForm
                    form={experienceForm}
                    setForm={setExperienceForm}
                    onSubmit={handleExperienceSubmit}
                    onCancel={() => {
                      setShowExperienceForm(false);
                      setEditingExperience(null);
                      setExperienceForm(EMPTY_EXPERIENCE);
                    }}
                    editingExperience={editingExperience}
                    loading={loading}
                  />
                )}
                <div className="space-y-4">
                  {experience.map(exp => (
                    <div
                      key={exp.id}
                      className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                            {exp.title}
                          </h3>
                          <p className="text-blue-600 dark:text-blue-400 font-medium">
                            {exp.company}
                          </p>
                          <p className="text-gray-600 dark:text-gray-300 text-sm">
                            {exp.location}
                          </p>
                          <p className="text-gray-500 dark:text-gray-400 text-sm">
                            {exp.period}
                          </p>
                          <p className="text-gray-700 dark:text-gray-300 mt-2">
                            {exp.description}
                          </p>
                        </div>
                        <div className="flex gap-2 ml-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleExperienceEdit(exp)}
                            disabled={loading}
                          >
                            Edit
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void handleExperienceDelete(exp.id)}
                            disabled={loading}
                            className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                          >
                            Delete
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Skills */}
            {activeTab === 'skills' && (
              <div>
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                    Manage Skills
                  </h2>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setShowSkillForm(true);
                      setEditingSkill(null);
                      setSkillForm(EMPTY_SKILL);
                    }}
                    disabled={loading}
                  >
                    Add New Skill
                  </Button>
                </div>
                {showSkillForm && (
                  <SkillForm
                    form={skillForm}
                    setForm={setSkillForm}
                    onSubmit={handleSkillSubmit}
                    onCancel={() => {
                      setShowSkillForm(false);
                      setEditingSkill(null);
                      setSkillForm(EMPTY_SKILL);
                    }}
                    editingSkill={editingSkill}
                    loading={loading}
                  />
                )}
                <div className="space-y-2">
                  {skills.map(skill => (
                    <div
                      key={skill.id}
                      className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 flex items-center gap-4"
                    >
                      <span className="text-2xl">{skill.icon || '💻'}</span>
                      <div className="flex-1">
                        <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                          {skill.name}{' '}
                          <span className="text-xs px-2 py-0.5 ml-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full">
                            {skill.category}
                          </span>
                        </h3>
                        <div className="flex items-center gap-3 mt-1">
                          <span className="text-xs px-2 py-0.5 bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-full capitalize">
                            {skill.tier}
                          </span>
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            order {skill.order}
                          </span>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleSkillEdit(skill)}
                          disabled={loading}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void handleSkillDelete(skill.id)}
                          disabled={loading}
                          className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                        >
                          Delete
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Education */}
            {activeTab === 'education' && (
              <div>
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                    Manage Education
                  </h2>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setShowEducationForm(true);
                      setEditingEducation(null);
                      setEducationForm(EMPTY_EDUCATION);
                    }}
                    disabled={loading}
                  >
                    Add New Education
                  </Button>
                </div>
                {showEducationForm && (
                  <EducationForm
                    form={educationForm}
                    setForm={setEducationForm}
                    onSubmit={handleEducationSubmit}
                    onCancel={() => {
                      setShowEducationForm(false);
                      setEditingEducation(null);
                      setEducationForm(EMPTY_EDUCATION);
                    }}
                    editingEducation={editingEducation}
                    loading={loading}
                  />
                )}
                <div className="space-y-4">
                  {education.map(ed => (
                    <div
                      key={ed.id}
                      className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                            {ed.degree}
                          </h3>
                          <p className="text-blue-600 dark:text-blue-400 font-medium">
                            {ed.school}
                          </p>
                          <p className="text-gray-500 dark:text-gray-400 text-sm">
                            {ed.location} · {ed.period}
                          </p>
                          {ed.description && (
                            <p className="text-gray-700 dark:text-gray-300 mt-2 text-sm">
                              {ed.description}
                            </p>
                          )}
                        </div>
                        <div className="flex gap-2 ml-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleEducationEdit(ed)}
                            disabled={loading}
                          >
                            Edit
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void handleEducationDelete(ed.id)}
                            disabled={loading}
                            className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                          >
                            Delete
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Certifications */}
            {activeTab === 'certifications' && (
              <div>
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                    Manage Certifications
                  </h2>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setShowCertForm(true);
                      setEditingCert(null);
                      setCertForm(EMPTY_CERTIFICATION);
                    }}
                    disabled={loading}
                  >
                    Add New Certification
                  </Button>
                </div>
                {showCertForm && (
                  <CertificationForm
                    form={certForm}
                    setForm={setCertForm}
                    onSubmit={handleCertSubmit}
                    onCancel={() => {
                      setShowCertForm(false);
                      setEditingCert(null);
                      setCertForm(EMPTY_CERTIFICATION);
                    }}
                    editingCertification={editingCert}
                    loading={loading}
                  />
                )}
                <div className="space-y-4">
                  {certifications.map(c => (
                    <div
                      key={c.id}
                      className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="text-base font-semibold text-gray-900 dark:text-white">
                            {c.name}
                          </h3>
                          <p className="text-gray-600 dark:text-gray-300 text-sm">
                            {c.issuer} · {c.issued_date}
                          </p>
                          {c.credential_url && (
                            <a
                              href={c.credential_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 dark:text-blue-400 text-sm hover:underline"
                            >
                              View credential →
                            </a>
                          )}
                        </div>
                        <div className="flex gap-2 ml-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleCertEdit(c)}
                            disabled={loading}
                          >
                            Edit
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void handleCertDelete(c.id)}
                            disabled={loading}
                            className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                          >
                            Delete
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Blog */}
            {activeTab === 'blog' && (
              <div>
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                    Manage Blog Posts
                  </h2>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setShowBlogPostForm(true);
                      setEditingPost(null);
                      setBlogPostForm(EMPTY_BLOG);
                    }}
                    disabled={loading}
                  >
                    Add New Blog Post
                  </Button>
                </div>
                {showBlogPostForm && (
                  <BlogPostForm
                    form={blogPostForm}
                    setForm={setBlogPostForm}
                    onSubmit={handleBlogPostSubmit}
                    onCancel={() => {
                      setShowBlogPostForm(false);
                      setEditingPost(null);
                      setBlogPostForm(EMPTY_BLOG);
                    }}
                    editingPost={editingPost}
                    loading={loading}
                  />
                )}
                <div className="space-y-4">
                  {blogPosts.map(post => (
                    <div
                      key={post.id}
                      className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                            {post.title}
                            {post.published_at && (
                              <span className="ml-2 px-2 py-1 bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 text-xs rounded-full">
                                Published
                              </span>
                            )}
                          </h3>
                          <p className="text-gray-600 dark:text-gray-300 text-sm">
                            Slug: {post.slug}
                          </p>
                          {post.excerpt && (
                            <p className="text-gray-700 dark:text-gray-300 mt-2">
                              {post.excerpt}
                            </p>
                          )}
                        </div>
                        <div className="flex gap-2 ml-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleBlogPostEdit(post)}
                            disabled={loading}
                          >
                            Edit
                          </Button>
                          {!post.published_at && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() =>
                                void handleBlogPostPublish(post.id)
                              }
                              disabled={loading}
                              className="text-green-600 dark:text-green-400 hover:text-green-700 dark:hover:text-green-300"
                            >
                              Publish
                            </Button>
                          )}
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void handleBlogPostDelete(post.id)}
                            disabled={loading}
                            className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                          >
                            Delete
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Categories */}
            {activeTab === 'categories' && (
              <div>
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                    Manage Categories
                  </h2>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => {
                      setShowCategoryForm(true);
                      setEditingCategory(null);
                      setCategoryForm(EMPTY_CATEGORY);
                    }}
                    disabled={loading}
                  >
                    Add New Category
                  </Button>
                </div>
                {showCategoryForm && (
                  <CategoryForm
                    form={categoryForm}
                    setForm={setCategoryForm}
                    onSubmit={e => void handleCategorySubmit(e)}
                    onCancel={() => {
                      setShowCategoryForm(false);
                      setEditingCategory(null);
                      setCategoryForm(EMPTY_CATEGORY);
                    }}
                    editingCategory={editingCategory}
                    loading={loading}
                  />
                )}
                <div className="space-y-4">
                  {categories.map(category => (
                    <div
                      key={category.id}
                      className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                            {category.name}
                          </h3>
                          <p className="text-gray-600 dark:text-gray-300 text-sm">
                            Slug: {category.slug}
                          </p>
                          {category.description && (
                            <p className="text-gray-700 dark:text-gray-300 mt-2">
                              {category.description}
                            </p>
                          )}
                        </div>
                        <div className="flex gap-2 ml-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleCategoryEdit(category)}
                            disabled={loading}
                          >
                            Edit
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              void handleCategoryDelete(category.id)
                            }
                            disabled={loading}
                            className="text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300"
                          >
                            Delete
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Security */}
            {activeTab === 'security' && (
              <div>
                {identityClient === null ? (
                  <div>
                    <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                      Security
                    </h2>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      A second factor needs the identity service, which this
                      bundle is not built against. Nothing to configure here.
                    </p>
                  </div>
                ) : (
                  <SecuritySection
                    key={linksEpoch}
                    client={identityClient}
                    oauthClient={identityClient}
                    availableProviders={oauthProviders}
                    passkeysClient={identityClient}
                  />
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
