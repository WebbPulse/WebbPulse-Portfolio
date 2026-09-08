import React from 'react';
import { GradientText } from '../common';
import {
  useSiteContent,
  useExperience,
  useProjects,
  useInViewReveal,
  useCountUp,
} from '../../hooks';
import type { Experience } from '../../services/api';

const calculateYearsFromExperience = (entries: Experience[] | null): number => {
  if (!entries || entries.length === 0) return 0;
  const now = new Date();
  let totalYears = 0;
  for (const exp of entries) {
    const start = new Date(exp.start_date);
    const end = exp.end_date ? new Date(exp.end_date) : now;
    totalYears +=
      (end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24 * 365.25);
  }
  return Math.round(totalYears);
};

const StatCard: React.FC<{
  value: number;
  label: string;
  trigger: boolean;
}> = ({ value, label, trigger }) => {
  const display = useCountUp(value, trigger);
  return (
    <div className="surface-glass surface-glass-hover rounded-2xl p-6 text-center">
      <div className="font-display text-4xl sm:text-5xl font-bold text-gradient leading-none">
        {display}
        <span className="text-accent-cyan-400">+</span>
      </div>
      <div className="mt-2 text-sm uppercase tracking-[0.16em] text-surface-400">
        {label}
      </div>
    </div>
  );
};

const ValueCard: React.FC<{
  title: string;
  description: string;
  icon?: string | null | undefined;
  index: number;
}> = ({ title, description, icon, index }) => {
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({
    threshold: 0.2,
  });
  return (
    <div
      ref={ref}
      style={{ animationDelay: `${index * 90}ms` }}
      className={`group relative surface-glass surface-glass-hover rounded-2xl p-7 transition-shadow duration-500 hover:shadow-glow-soft ${isInView ? 'animate-fade-in-up' : 'opacity-0'}`}
    >
      <div className="text-3xl mb-4">{icon ?? '✨'}</div>
      <h4 className="font-display text-xl font-semibold text-surface-50 mb-2">
        {title}
      </h4>
      <p className="text-surface-300 leading-relaxed text-sm">{description}</p>
    </div>
  );
};

export const About: React.FC = () => {
  const { data: site } = useSiteContent();
  const { data: experience } = useExperience();
  const { data: projects } = useProjects();

  const { ref: sectionRef, isInView: sectionInView } =
    useInViewReveal<HTMLDivElement>({ threshold: 0.1 });

  const years = calculateYearsFromExperience(experience);
  const projectCount = projects?.length ?? 0;
  const paragraphs = site?.about_paragraphs ?? [];
  const values = site?.about_values ?? [];
  const profileImage = site?.profile_image_url ?? '/headshot.jpg';

  return (
    <section id="about" className="relative py-24 sm:py-32 overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-b from-surface-950 via-surface-900 to-surface-950 pointer-events-none" />

      <div
        ref={sectionRef}
        className="relative z-10 max-w-7xl mx-auto px-6 sm:px-8"
      >
        <div className="text-center mb-16 max-w-2xl mx-auto">
          <span className="inline-block text-xs uppercase tracking-[0.2em] text-accent-cyan-400 mb-4">
            About
          </span>
          <h2 className="font-display text-4xl sm:text-5xl font-bold text-surface-50 mb-4">
            A bit about <GradientText as="span">me</GradientText>
          </h2>
          <p className="text-surface-300 text-lg">
            {site?.footer_tagline ??
              'Software engineer focused on building reliable, privacy-conscious systems.'}
          </p>
        </div>

        <div className="grid lg:grid-cols-5 gap-12 items-start">
          {/* Profile column */}
          <div className="lg:col-span-2 flex flex-col items-center lg:items-start">
            <div className="relative">
              {/* Animated gradient ring */}
              <div className="absolute inset-0 rounded-full bg-gradient-conic from-accent-cyan-500 via-accent-violet-500 via-accent-fuchsia-500 to-accent-cyan-500 animate-slow-spin blur-md opacity-70" />
              <div className="relative w-64 h-64 sm:w-72 sm:h-72 rounded-full p-[3px] bg-gradient-conic from-accent-cyan-400 via-accent-violet-400 via-accent-fuchsia-400 to-accent-cyan-400">
                <img
                  src={profileImage}
                  alt="Tyler Webb"
                  className="w-full h-full rounded-full object-cover bg-surface-900"
                />
              </div>
            </div>

            <div className="mt-10 grid grid-cols-2 gap-4 w-full max-w-sm">
              <StatCard
                value={years}
                label="Years"
                trigger={sectionInView && years > 0}
              />
              <StatCard
                value={projectCount}
                label="Projects"
                trigger={sectionInView && projectCount > 0}
              />
            </div>
          </div>

          {/* Bio column */}
          <div className="lg:col-span-3 space-y-5">
            {paragraphs.length > 0 ? (
              paragraphs.map((p, i) => (
                <p key={i} className="text-surface-200 text-lg leading-relaxed">
                  {p}
                </p>
              ))
            ) : (
              <div className="space-y-4">
                <div className="h-4 bg-surface-800 rounded animate-pulse" />
                <div className="h-4 bg-surface-800 rounded animate-pulse w-11/12" />
                <div className="h-4 bg-surface-800 rounded animate-pulse w-10/12" />
              </div>
            )}
          </div>
        </div>

        {/* Values */}
        {values.length > 0 && (
          <div className="mt-24">
            <div className="text-center mb-10">
              <span className="inline-block text-xs uppercase tracking-[0.2em] text-accent-violet-400 mb-3">
                Principles
              </span>
              <h3 className="font-display text-3xl font-bold text-surface-50">
                What I value
              </h3>
            </div>
            <div className="grid md:grid-cols-3 gap-6">
              {values.map((v, i) => (
                <ValueCard
                  key={`${v.title}-${i}`}
                  title={v.title}
                  description={v.description}
                  icon={v.icon}
                  index={i}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
};
