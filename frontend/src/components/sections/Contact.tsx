import React from 'react';
import { GradientText, AnimatedOrb, GradientPanel } from '../common';
import { useSiteContent, useInViewReveal } from '../../hooks';
import { SocialIcon } from '../../utils';

const ContactTile: React.FC<{
  href: string;
  platform: string;
  label: string;
  value: string;
  glow: string;
}> = ({ href, platform, label, value, glow }) => (
  <a
    href={href}
    target={href.startsWith('mailto:') ? undefined : '_blank'}
    rel={href.startsWith('mailto:') ? undefined : 'noopener noreferrer'}
    aria-label={label}
    className={`group surface-glass surface-glass-hover rounded-2xl p-6 flex items-center gap-4 transition-all duration-500 hover:-translate-y-0.5 ${glow} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-950`}
  >
    <span className="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-accent-cyan-500/20 via-accent-violet-500/20 to-accent-fuchsia-500/20 border border-accent-violet-500/30 text-surface-100">
      <SocialIcon platform={platform} className="w-5 h-5" />
    </span>
    <div className="flex-1 min-w-0">
      <div className="text-xs uppercase tracking-[0.16em] text-accent-cyan-400">
        {label}
      </div>
      <div className="font-display text-base text-surface-50 truncate">
        {value}
      </div>
    </div>
    <span className="text-surface-400 group-hover:text-surface-100 group-hover:translate-x-1 transition-all">
      →
    </span>
  </a>
);

/** The Contact section, with the links from site content. */
export const Contact: React.FC = () => {
  const { data } = useSiteContent();
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({ threshold: 0.1 });

  const email = data?.email ?? 'tyler@webbpulse.com';
  const github = data?.github_url ?? 'https://github.com/Tylert2610';
  const linkedin =
    data?.linkedin_url ?? 'https://www.linkedin.com/in/tylert2610/';

  return (
    <section
      id="contact"
      className="relative py-24 sm:py-32 overflow-hidden bg-surface-950"
    >
      <div className="absolute inset-0 bg-mesh-1 opacity-60 pointer-events-none" />
      <AnimatedOrb
        gradient="from-accent-cyan-500 to-accent-violet-500"
        size="w-[28rem] h-[28rem]"
        position="-top-32 -left-20"
        variant={1}
        opacity="opacity-25"
      />
      <AnimatedOrb
        gradient="from-accent-fuchsia-500 to-accent-violet-500"
        size="w-[24rem] h-[24rem]"
        position="-bottom-24 -right-16"
        variant={3}
        opacity="opacity-25"
      />

      <div
        ref={ref}
        className={`relative z-10 max-w-4xl mx-auto px-6 sm:px-8 ${isInView ? 'animate-fade-in-up' : 'opacity-0'}`}
      >
        <GradientPanel className="px-8 py-14 sm:px-12 sm:py-20">
          <div className="text-center mb-10">
            <span className="inline-block text-xs uppercase tracking-[0.2em] text-accent-cyan-400 mb-4">
              Get in touch
            </span>
            <h2 className="font-display text-4xl sm:text-5xl font-bold text-surface-50 mb-4">
              Let's <GradientText as="span">build something</GradientText>
            </h2>
            <p className="text-surface-300 text-lg max-w-xl mx-auto">
              Open to interesting work, side projects, or a chat about software,
              networking, or infra.
            </p>
          </div>

          <div className="grid sm:grid-cols-1 gap-3 max-w-xl mx-auto">
            <ContactTile
              href={`mailto:${email}`}
              platform="website"
              label="Email"
              value={email}
              glow="hover:shadow-glow-cyan"
            />
            <ContactTile
              href={github}
              platform="github"
              label="GitHub"
              value={github.replace(/^https?:\/\//, '')}
              glow="hover:shadow-glow-violet"
            />
            <ContactTile
              href={linkedin}
              platform="linkedin"
              label="LinkedIn"
              value={linkedin.replace(/^https?:\/\//, '')}
              glow="hover:shadow-glow-fuchsia"
            />
          </div>
        </GradientPanel>
      </div>
    </section>
  );
};
