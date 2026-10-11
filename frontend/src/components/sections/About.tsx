import React from 'react';
import { useInViewReveal, useCountUp } from '../../hooks';
import { getExperience, getProjects, getSiteContent } from '../../content';
import type { Experience } from '../../content';
import {
  MonoLabel,
  RegistrationMarks,
  SectionHeading,
  Sheet,
} from '../drawing';

/** Whole years of work across every experience entry, open roles running to today. */
const calculateYearsFromExperience = (entries: Experience[]): number => {
  if (entries.length === 0) return 0;
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

/** A counted figure in a title block cell. */
const Figure: React.FC<{
  value: number;
  label: string;
  trigger: boolean;
}> = ({ value, label, trigger }) => {
  const display = useCountUp(value, trigger);
  return (
    <div className="border-b border-r border-line px-4 py-4">
      <dt className="mono-label">{label}</dt>
      <dd className="mt-2 font-mono text-3xl font-medium tabular-nums text-ink">
        {display}
        <span className="text-ink-faint">+</span>
      </dd>
    </div>
  );
};

/** One principle from site content, numbered like a drawing note. */
const ValueNote: React.FC<{
  title: string;
  description: string;
  index: number;
}> = ({ title, description, index }) => {
  const { ref, isInView } = useInViewReveal<HTMLLIElement>({
    threshold: 0.2,
  });
  return (
    <li
      ref={ref}
      style={{ animationDelay: `${index * 80}ms` }}
      className={`border-b border-r border-line p-6 ${isInView ? 'motion-safe:animate-fade-in-up' : 'motion-safe:opacity-0'}`}
    >
      <span className="font-mono text-xs text-accent tabular-nums">
        N{String(index + 1).padStart(2, '0')}
      </span>
      <h4 className="mt-3 text-lg font-semibold text-ink">{title}</h4>
      <p className="mt-2 text-sm leading-relaxed text-ink-muted">
        {description}
      </p>
    </li>
  );
};

/** The About section, over site content with a static fallback. */
export const About: React.FC = () => {
  const site = getSiteContent();
  const experience = getExperience();
  const projects = getProjects();

  const { ref: sectionRef, isInView: sectionInView } =
    useInViewReveal<HTMLDivElement>({ threshold: 0.1 });

  const years = calculateYearsFromExperience(experience);
  const projectCount = projects.length;
  const paragraphs = site.about_paragraphs;
  const values = site.about_values;
  const profileImage = site.profile_image_url ?? '/headshot.jpg';

  return (
    <section
      id="about"
      aria-labelledby="about-title"
      className="border-b border-line py-20 sm:py-28"
    >
      <Sheet>
        <div ref={sectionRef}>
          <SectionHeading
            index="02"
            label="About"
            id="about-title"
            title="A bit about me"
          >
            {site.footer_tagline ??
              'Software engineer focused on building reliable, privacy-conscious systems.'}
          </SectionHeading>

          <div className="grid items-start gap-12 lg:grid-cols-12">
            <div className="lg:col-span-4">
              <figure className="relative w-full max-w-xs">
                <RegistrationMarks />
                <div className="border border-line bg-paper-raised p-2">
                  <img
                    src={profileImage}
                    alt="Tyler Webb"
                    className="aspect-square w-full object-cover grayscale-[15%]"
                  />
                </div>
                <figcaption className="mt-3 flex items-center justify-between">
                  <MonoLabel>Tyler Webb</MonoLabel>
                  <MonoLabel>Fig. 2</MonoLabel>
                </figcaption>
              </figure>

              <dl className="mt-8 grid max-w-xs grid-cols-2 border-l border-t border-line">
                <Figure
                  value={years}
                  label="Years"
                  trigger={sectionInView && years > 0}
                />
                <Figure
                  value={projectCount}
                  label="Projects"
                  trigger={sectionInView && projectCount > 0}
                />
              </dl>
            </div>

            <div className="space-y-5 lg:col-span-8">
              {paragraphs.map((p, i) => (
                <p
                  key={i}
                  className="max-w-2xl text-lg leading-relaxed text-ink-muted first:text-xl first:text-ink"
                >
                  {p}
                </p>
              ))}
            </div>
          </div>

          {values.length > 0 && (
            <div className="mt-20">
              <div className="mb-6 flex items-center gap-3">
                <MonoLabel>Principles</MonoLabel>
                <span className="h-px flex-1 bg-line" aria-hidden="true" />
              </div>
              <h3 className="sr-only">What I value</h3>
              <ul className="grid border-l border-t border-line md:grid-cols-3">
                {values.map((v, i) => (
                  <ValueNote
                    key={`${v.title}-${i}`}
                    title={v.title}
                    description={v.description}
                    index={i}
                  />
                ))}
              </ul>
            </div>
          )}
        </div>
      </Sheet>
    </section>
  );
};
