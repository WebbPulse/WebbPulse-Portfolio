import React from 'react';
import { GradientText } from '../common';
import {
  useExperience,
  useEducation,
  useCertifications,
  useInViewReveal,
} from '../../hooks';
import type {
  Experience as ExperienceType,
  Education as EducationType,
  Certification as CertificationType,
} from '../../services/api';

const ExperienceCard: React.FC<{ item: ExperienceType; index: number }> = ({
  item,
  index,
}) => {
  const isEven = index % 2 === 0;
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({
    threshold: 0.15,
  });

  return (
    <div
      className={`relative flex flex-col md:flex-row ${isEven ? 'md:flex-row' : 'md:flex-row-reverse'}`}
    >
      <div className="absolute left-4 md:left-1/2 -translate-x-1/2 z-10 flex items-center justify-center">
        <span className="absolute w-4 h-4 rounded-full bg-accent-violet-500 animate-glow-pulse" />
        <span className="relative w-3 h-3 rounded-full bg-gradient-to-br from-accent-cyan-400 to-accent-fuchsia-500 border-2 border-surface-950" />
      </div>

      <div
        ref={ref}
        className={`ml-14 md:ml-0 md:w-[calc(50%-2rem)] ${isEven ? 'md:mr-auto md:pr-12 md:text-right' : 'md:ml-auto md:pl-12'} ${isInView ? 'animate-fade-in-up' : 'opacity-0'}`}
      >
        <div className="surface-glass surface-glass-hover rounded-2xl p-6 transition-all duration-500 hover:shadow-glow-soft">
          <div
            className={`flex flex-col gap-1 mb-3 ${isEven ? 'md:items-end' : 'md:items-start'}`}
          >
            <span className="text-xs uppercase tracking-[0.18em] text-accent-cyan-400">
              {item.period}
            </span>
            <h3 className="font-display text-xl font-semibold text-surface-50">
              {item.title}
            </h3>
            <p className="text-accent-violet-300 font-medium">{item.company}</p>
            <p className="text-surface-400 text-sm">{item.location}</p>
          </div>

          <p
            className={`text-surface-300 text-sm leading-relaxed mb-4 ${isEven ? 'md:text-right' : ''}`}
          >
            {item.description}
          </p>

          <div
            className={`flex flex-wrap gap-1.5 mb-4 ${isEven ? 'md:justify-end' : ''}`}
          >
            {item.technologies.map((tech) => (
              <span
                key={tech}
                className="px-2.5 py-0.5 text-xs rounded-full bg-surface-800 border border-surface-700 text-surface-200"
              >
                {tech}
              </span>
            ))}
          </div>

          {item.achievements.length > 0 && (
            <ul className="space-y-1.5">
              {item.achievements.map((a, i) => (
                <li
                  key={i}
                  className={`text-sm text-surface-300 flex items-start gap-2 ${isEven ? 'md:flex-row-reverse md:text-right' : ''}`}
                >
                  <svg
                    className="flex-shrink-0 w-4 h-4 mt-0.5 text-accent-cyan-400"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};

const EducationCard: React.FC<{ item: EducationType; index: number }> = ({
  item,
  index,
}) => {
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({ threshold: 0.2 });
  return (
    <div
      ref={ref}
      style={{ animationDelay: `${index * 80}ms` }}
      className={`group surface-glass surface-glass-hover rounded-2xl p-6 transition-shadow duration-500 hover:shadow-glow-violet ${isInView ? 'animate-fade-in-up' : 'opacity-0'}`}
    >
      <div className="flex items-start justify-between gap-4 mb-3">
        <div>
          <h4 className="font-display text-lg font-semibold text-surface-50 leading-tight">
            {item.degree}
          </h4>
          <p className="text-accent-violet-300 mt-1">{item.school}</p>
          <p className="text-surface-400 text-sm">{item.location}</p>
        </div>
        <span className="text-xs uppercase tracking-[0.16em] text-accent-cyan-400 whitespace-nowrap">
          {item.period}
        </span>
      </div>
      {item.description && (
        <p className="text-surface-300 text-sm leading-relaxed">
          {item.description}
        </p>
      )}
    </div>
  );
};

const CertificationCard: React.FC<{
  item: CertificationType;
  index: number;
}> = ({ item, index }) => {
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({ threshold: 0.2 });
  const year = item.issued_date?.slice(0, 4);
  const inner = (
    <div className="surface-glass surface-glass-hover rounded-2xl p-6 h-full transition-shadow duration-500 hover:shadow-glow-cyan">
      <div className="flex items-center justify-center w-14 h-14 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-accent-cyan-500/20 to-accent-violet-500/20 border border-accent-violet-500/30">
        <span className="text-2xl" aria-hidden="true">
          🏆
        </span>
      </div>
      <h4 className="font-display text-base font-semibold text-surface-50 text-center mb-1.5 leading-snug">
        {item.name}
      </h4>
      <p className="text-surface-300 text-sm text-center">{item.issuer}</p>
      {year && (
        <p className="mt-2 text-xs text-accent-cyan-400 text-center uppercase tracking-[0.16em]">
          {year}
        </p>
      )}
    </div>
  );
  return (
    <div
      ref={ref}
      style={{ animationDelay: `${index * 70}ms` }}
      className={isInView ? 'animate-fade-in-up' : 'opacity-0'}
    >
      {item.credential_url ? (
        <a
          href={item.credential_url}
          target="_blank"
          rel="noopener noreferrer"
          className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-950 rounded-2xl"
        >
          {inner}
        </a>
      ) : (
        inner
      )}
    </div>
  );
};

const SkeletonCard: React.FC = () => (
  <div className="surface-glass rounded-2xl p-6 animate-pulse">
    <div className="h-3 bg-surface-800 rounded w-1/3 mb-3" />
    <div className="h-4 bg-surface-800 rounded w-2/3 mb-2" />
    <div className="h-3 bg-surface-800 rounded w-1/2" />
  </div>
);

/** The work history timeline, with education and certifications. */
export const Experience: React.FC = () => {
  const {
    data: experience,
    loading: expLoading,
    error: expError,
  } = useExperience();
  const { data: education, loading: eduLoading } = useEducation();
  const { data: certifications, loading: certLoading } = useCertifications();

  return (
    <section
      id="experience"
      className="relative py-24 sm:py-32 overflow-hidden bg-surface-950"
    >
      <div className="absolute inset-0 bg-gradient-to-b from-surface-950 via-surface-900 to-surface-950 pointer-events-none" />

      <div className="relative z-10 max-w-7xl mx-auto px-6 sm:px-8">
        <div className="text-center mb-16 max-w-2xl mx-auto">
          <span className="inline-block text-xs uppercase tracking-[0.2em] text-accent-fuchsia-400 mb-4">
            Experience
          </span>
          <h2 className="font-display text-4xl sm:text-5xl font-bold text-surface-50 mb-4">
            Where I've <GradientText as="span">worked</GradientText>
          </h2>
          <p className="text-surface-300 text-lg">
            Roles, schools, and certs that shaped where I am.
          </p>
        </div>

        {/* Timeline */}
        <div className="relative">
          <div className="absolute left-4 md:left-1/2 -translate-x-1/2 top-0 bottom-0 w-px bg-gradient-to-b from-accent-cyan-500/0 via-accent-violet-500/60 to-accent-fuchsia-500/0" />

          {expLoading && (
            <div className="space-y-12">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          )}
          {expError && (
            <p className="text-center text-surface-400">
              Couldn't load experience.
            </p>
          )}
          {!expLoading && !expError && (
            <div className="space-y-12">
              {experience?.map((item, idx) => (
                <ExperienceCard key={item.id} item={item} index={idx} />
              ))}
            </div>
          )}
        </div>

        <div className="mt-24">
          <div className="text-center mb-10">
            <span className="inline-block text-xs uppercase tracking-[0.2em] text-accent-violet-400 mb-3">
              Education
            </span>
            <h3 className="font-display text-3xl font-bold text-surface-50">
              Where I learned the basics
            </h3>
          </div>
          {eduLoading && (
            <div className="grid md:grid-cols-2 gap-6">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          )}
          {!eduLoading && (education?.length ?? 0) > 0 && (
            <div className="grid md:grid-cols-2 gap-6">
              {education?.map((e, i) => (
                <EducationCard key={e.id} item={e} index={i} />
              ))}
            </div>
          )}
        </div>

        <div className="mt-20">
          <div className="text-center mb-10">
            <span className="inline-block text-xs uppercase tracking-[0.2em] text-accent-cyan-400 mb-3">
              Certifications
            </span>
            <h3 className="font-display text-3xl font-bold text-surface-50">
              Credentials
            </h3>
          </div>
          {certLoading && (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </div>
          )}
          {!certLoading && (certifications?.length ?? 0) > 0 && (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {certifications?.map((c, i) => (
                <CertificationCard key={c.id} item={c} index={i} />
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
