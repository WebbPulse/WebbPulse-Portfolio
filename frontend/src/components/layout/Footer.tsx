import React from 'react';
import { Link } from 'react-router-dom';
import { SocialIcon } from '../../utils';
import { useSiteContent } from '../../hooks';

/** The site footer, with the social links and tagline from site content. */
const Footer: React.FC = () => {
  const { data } = useSiteContent();
  const currentYear = new Date().getFullYear();

  const tagline =
    data?.footer_tagline ??
    'Software engineer focused on building reliable, privacy-conscious systems.';
  const email = data?.email;
  const github = data?.github_url;
  const linkedin = data?.linkedin_url;

  const links: { platform: string; url: string; label: string }[] = [];
  if (github) links.push({ platform: 'github', url: github, label: 'GitHub' });
  if (linkedin)
    links.push({ platform: 'linkedin', url: linkedin, label: 'LinkedIn' });

  return (
    <footer className="relative bg-surface-950 border-t border-surface-800">
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-accent-violet-500/60 to-transparent" />

      <div className="max-w-7xl mx-auto px-6 sm:px-8 py-12">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-8">
          <div className="space-y-2 max-w-md">
            <Link
              to="/"
              className="font-display text-xl font-bold text-surface-50 inline-block"
            >
              Tyler <span className="text-gradient">Webb</span>
            </Link>
            <p className="text-surface-400 text-sm leading-relaxed">
              {tagline}
            </p>
          </div>

          <div className="flex items-center gap-3">
            {email && (
              <a
                href={`mailto:${email}`}
                aria-label="Email"
                className="w-10 h-10 inline-flex items-center justify-center rounded-full surface-glass surface-glass-hover text-surface-200 hover:text-surface-50 transition-colors"
              >
                <svg
                  className="w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true"
                >
                  <path d="M3 8l9 6 9-6M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </a>
            )}
            {links.map(link => (
              <a
                key={link.platform}
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={link.label}
                className="w-10 h-10 inline-flex items-center justify-center rounded-full surface-glass surface-glass-hover text-surface-200 hover:text-surface-50 transition-colors"
              >
                <SocialIcon platform={link.platform} className="w-4 h-4" />
              </a>
            ))}
          </div>
        </div>

        <div className="mt-10 pt-6 border-t border-surface-800 flex flex-col sm:flex-row gap-2 sm:items-center sm:justify-between text-xs text-surface-500">
          <div className="flex items-center gap-4">
            <p>© {currentYear} Tyler Webb</p>
            <Link
              to="/privacy"
              className="text-surface-500 hover:text-surface-300 transition-colors"
            >
              Privacy
            </Link>
          </div>
          <p className="text-surface-600">
            Built with React, FastAPI, and a lot of caffeine.
          </p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
