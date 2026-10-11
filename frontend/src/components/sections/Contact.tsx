import React from 'react';
import { useInViewReveal } from '../../hooks';
import { getSiteContent } from '../../content';
import { SocialIcon } from '../../utils';
import { RegistrationMarks, SectionHeading, Sheet } from '../drawing';

/** One contact channel as a row of the contact table. */
const ContactRow: React.FC<{
  href: string;
  platform: string;
  label: string;
  value: string;
}> = ({ href, platform, label, value }) => {
  const external = !href.startsWith('mailto:');
  return (
    <li className="border-b border-line">
      <a
        href={href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
        className="group grid grid-cols-[2rem_1fr_auto] items-center gap-3 py-4 transition-colors hover:bg-accent-soft sm:grid-cols-[2rem_8rem_1fr_auto] sm:px-3 sm:-mx-3"
      >
        <span className="flex h-8 w-8 items-center justify-center border border-line text-ink">
          {platform === 'email' ? (
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
          ) : (
            <SocialIcon platform={platform} className="h-3.5 w-3.5" />
          )}
        </span>
        <span className="mono-label hidden sm:block">{label}</span>
        <span className="min-w-0 truncate text-base text-ink">
          <span className="sr-only sm:hidden">{label}: </span>
          {value}
        </span>
        <span
          aria-hidden="true"
          className="font-mono text-ink-muted transition-transform group-hover:text-ink motion-safe:group-hover:translate-x-0.5"
        >
          {external ? '↗' : '→'}
        </span>
      </a>
    </li>
  );
};

/** The Contact section, with the links from site content. */
export const Contact: React.FC = () => {
  const data = getSiteContent();
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({ threshold: 0.1 });

  const email = data.email ?? 'tyler@webbpulse.com';
  const github = data.github_url ?? 'https://github.com/Tylert2610';
  const linkedin =
    data.linkedin_url ?? 'https://www.linkedin.com/in/tylert2610/';

  return (
    <section
      id="contact"
      aria-labelledby="contact-title"
      className="py-20 sm:py-28"
    >
      <Sheet>
        <div
          ref={ref}
          className={
            isInView
              ? 'motion-safe:animate-fade-in-up'
              : 'motion-safe:opacity-0'
          }
        >
          <SectionHeading
            index="07"
            label="Get in touch"
            id="contact-title"
            title="Let's build something"
          >
            Open to interesting work, side projects, or a chat about software,
            networking, or infra.
          </SectionHeading>

          <div className="relative max-w-3xl border border-line bg-paper-raised/70 px-5 sm:px-8">
            <RegistrationMarks />
            <ul className="-mb-px">
              <ContactRow
                href={`mailto:${email}`}
                platform="email"
                label="Email"
                value={email}
              />
              <ContactRow
                href={github}
                platform="github"
                label="GitHub"
                value={github.replace(/^https?:\/\//, '')}
              />
              <ContactRow
                href={linkedin}
                platform="linkedin"
                label="LinkedIn"
                value={linkedin.replace(/^https?:\/\//, '')}
              />
            </ul>
          </div>
        </div>
      </Sheet>
    </section>
  );
};
