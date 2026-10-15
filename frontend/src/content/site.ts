import type { SiteContent } from './types';

/** The copy and links behind the hero, about, contact and footer. */
export const siteContent: SiteContent = {
  hero_title: "Hi, I'm Tyler Webb",
  hero_subtitle: 'Software Engineer',
  hero_description:
    'Software engineer building reliable, well-crafted software. Background in network engineering and full-stack web.',
  about_paragraphs: [
    "Hi, I'm Tyler. I'm a software engineer who enjoys building reliable, well-crafted systems.",
    'Outside of work I build personal projects (this site included), usually full-stack TypeScript and React on the frontend, Python and FastAPI on the backend, deployed on AWS via Terraform.',
  ],
  about_values: [
    {
      title: 'Clean Code',
      description:
        'Writing maintainable, well-documented code that others can easily understand and build upon.',
      icon: '✨',
    },
    {
      title: 'User Experience',
      description:
        'Creating intuitive, accessible interfaces that provide delightful user experiences.',
      icon: '🎨',
    },
    {
      title: 'Continuous Learning',
      description:
        'Staying up-to-date with the latest technologies and best practices in software engineering.',
      icon: '📚',
    },
  ],
  profile_image_url: '/headshot.jpg',
  resume_url: '',
  email: 'tyler@webbpulse.com',
  github_url: 'https://github.com/T-Webb1',
  linkedin_url: 'https://www.linkedin.com/in/tylert2610/',
  footer_tagline:
    'Software engineer focused on building reliable, maintainable systems.',
  project_sort_mode: 'manual',
  id: 1,
  created_at: '2026-05-10T02:22:31.563043Z',
  updated_at: '2026-09-13T04:25:51.766260Z',
};
