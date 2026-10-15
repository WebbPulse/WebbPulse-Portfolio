import React from 'react';
import { Link } from 'react-router-dom';
import { SocialIcon } from '../../utils';
import { getSiteContent } from '../../content';
import { MonoLabel, Sheet } from '../drawing';

/**
 * The site footer, drawn as the title block of the sheet: who drew it, the
 * contact links from site content, and the privacy page.
 */
const Footer: React.FC = () => {
  const data = getSiteContent();
  const currentYear = new Date().getFullYear();

  const tagline =
    data.footer_tagline ??
    'Software engineer focused on building reliable, privacy-conscious systems.';
  const email = data.email;
  const github = data.github_url;
  const linkedin = data.linkedin_url;

  const links: { platform: string; url: string; label: string }[] = [];
  if (github) links.push({ platform: 'github', url: github, label: 'GitHub' });
  if (linkedin)
    links.push({ platform: 'linkedin', url: linkedin, label: 'LinkedIn' });

  const cell = 'border-b border-r border-line px-4 py-3 min-w-0';

  return (
    <footer className="mt-auto border-t border-line bg-paper">
      <Sheet className="py-10 sm:py-14">
        <div className="grid grid-cols-1 border-l border-t border-line md:grid-cols-12">
          <div className={`${cell} md:col-span-12 lg:col-span-6`}>
            <MonoLabel as="p">Drawn by</MonoLabel>
            <Link
              to="/"
              className="mt-1 inline-block text-lg font-semibold tracking-tight text-ink hover:text-accent transition-colors"
            >
              Tyler Webb
            </Link>
            <p className="mt-1 max-w-md text-sm leading-relaxed text-ink-muted">
              {tagline}
            </p>
          </div>

          <div className={`${cell} md:col-span-6 lg:col-span-3`}>
            <MonoLabel as="p">Contact</MonoLabel>
            <ul className="mt-2 space-y-1.5">
              {email && (
                <li>
                  <a
                    href={`mailto:${email}`}
                    className="inline-flex items-center gap-2 text-sm text-ink-muted hover:text-ink transition-colors"
                  >
                    <svg
                      className="h-3.5 w-3.5"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.75"
                      aria-hidden="true"
                    >
                      <path d="M3 7l9 6 9-6M4 5h16v14H4z" />
                    </svg>
                    Email
                  </a>
                </li>
              )}
              {links.map((link) => (
                <li key={link.platform}>
                  <a
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 text-sm text-ink-muted hover:text-ink transition-colors"
                  >
                    <SocialIcon
                      platform={link.platform}
                      className="h-3.5 w-3.5"
                    />
                    {link.label}
                  </a>
                </li>
              ))}
              {!email && links.length === 0 && (
                <li className="text-sm text-ink-faint">Not listed</li>
              )}
            </ul>
          </div>

          <div className={`${cell} md:col-span-6 lg:col-span-3`}>
            <MonoLabel as="p">Sheet</MonoLabel>
            <p className="mt-1 break-words font-mono text-sm text-ink">
              portfolio.webbpulse.com
            </p>
            <p className="mt-2 font-mono text-xs text-ink-muted">
              React, FastAPI, AWS Lambda
            </p>
          </div>

          <div
            className={`${cell} flex flex-wrap items-center justify-between gap-3 md:col-span-12`}
          >
            <p
              className="font-mono text-xs text-ink-muted"
              suppressHydrationWarning
            >
              © {currentYear} Tyler Webb
            </p>
            <Link
              to="/privacy"
              className="font-mono text-xs text-ink-muted hover:text-ink underline decoration-line-strong underline-offset-4 transition-colors"
            >
              Privacy
            </Link>
          </div>
        </div>
      </Sheet>
    </footer>
  );
};

export default Footer;
