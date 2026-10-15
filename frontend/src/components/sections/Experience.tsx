import React from 'react';
import { useInViewReveal } from '../../hooks';
import { getCertifications, getEducation, getExperience } from '../../content';
import type {
  Experience as ExperienceType,
  Education as EducationType,
  Certification as CertificationType,
} from '../../content';
import { MonoLabel, SectionHeading, Sheet } from '../drawing';

/** One role on the timeline: period beside the spine, notes to its right. */
const ExperienceRow: React.FC<{ item: ExperienceType; index: number }> = ({
  item,
  index,
}) => {
  const { ref, isInView } = useInViewReveal<HTMLLIElement>({
    threshold: 0.15,
  });

  return (
    <li
      ref={ref}
      className={`grid md:grid-cols-12 ${isInView ? 'motion-safe:animate-fade-in-up' : 'motion-safe:opacity-0'}`}
    >
      <div className="relative pt-8 md:col-span-3 md:border-r md:border-line-strong md:py-8 md:pr-8">
        <span
          className={`absolute -right-[5px] top-[2.35rem] hidden h-[9px] w-[9px] border md:block ${index === 0 ? 'border-accent bg-accent' : 'border-line-strong bg-paper'}`}
          aria-hidden="true"
        />
        <div className="flex items-center gap-3 md:block">
          <span className="font-mono text-xs text-accent">
            R{String(index + 1).padStart(2, '0')}
          </span>
          <p className="font-mono text-sm text-ink md:mt-2">{item.period}</p>
        </div>
        <p className="mt-1 text-sm text-ink-muted">{item.location}</p>
      </div>

      <div className="border-b border-line pb-8 pt-3 md:col-span-9 md:py-8 md:pl-8">
        <h3 className="text-xl font-semibold tracking-tight text-ink">
          {item.title}
        </h3>
        <p className="mt-0.5 text-ink-muted">{item.company}</p>

        <p className="mt-4 max-w-3xl leading-relaxed text-ink-muted">
          {item.description}
        </p>

        {item.achievements.length > 0 && (
          <ul className="mt-4 max-w-3xl space-y-2">
            {item.achievements.map((a, i) => (
              <li
                key={i}
                className="grid grid-cols-[1.5rem_1fr] text-sm leading-relaxed text-ink-muted"
              >
                <span
                  className="mt-[0.6rem] h-px w-3 bg-line-strong"
                  aria-hidden="true"
                />
                <span>{a}</span>
              </li>
            ))}
          </ul>
        )}

        {item.technologies.length > 0 && (
          <p className="mt-5 font-mono text-xs leading-relaxed text-ink-muted">
            <span className="sr-only">Technologies: </span>
            {item.technologies.join(' / ')}
          </p>
        )}
      </div>
    </li>
  );
};

/** One school as a title block cell. */
const EducationCell: React.FC<{ item: EducationType }> = ({ item }) => (
  <li className="border-b border-r border-line p-5">
    <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <h4 className="min-w-0 text-base font-semibold leading-snug text-ink">
        {item.degree}
      </h4>
      <span className="whitespace-nowrap font-mono text-xs text-ink-muted">
        {item.period}
      </span>
    </div>
    <p className="mt-1 text-sm text-ink-muted">
      {item.school}
      {item.location ? `, ${item.location}` : ''}
    </p>
    {item.description && (
      <p className="mt-3 text-sm leading-relaxed text-ink-muted">
        {item.description}
      </p>
    )}
  </li>
);

/** One certification as a row of the credentials table. */
const CertificationRow: React.FC<{ item: CertificationType }> = ({ item }) => {
  const year = item.issued_date?.slice(0, 4);
  return (
    <tr className="border-b border-line">
      <td className="py-3 pr-4 align-top text-sm text-ink">
        {item.credential_url ? (
          <a
            href={item.credential_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ink-link text-ink"
          >
            {item.name}
            <span aria-hidden="true"> ↗</span>
          </a>
        ) : (
          item.name
        )}
      </td>
      <td className="hidden py-3 pr-4 align-top text-sm text-ink-muted sm:table-cell">
        {item.issuer}
      </td>
      <td className="py-3 text-right align-top font-mono text-xs text-ink-muted tabular-nums">
        {year ?? ''}
      </td>
    </tr>
  );
};

/** A small sub-heading inside the section, with a running rule. */
const SubHeading: React.FC<{ label: string; title: string }> = ({
  label,
  title,
}) => (
  <div className="mb-6 flex items-baseline gap-3">
    <MonoLabel>{label}</MonoLabel>
    <h3 className="text-lg font-semibold text-ink">{title}</h3>
    <span className="h-px flex-1 self-center bg-line" aria-hidden="true" />
  </div>
);

/** The work history, with education and certifications. */
export const Experience: React.FC = () => {
  const experience = getExperience();
  const education = getEducation();
  const certifications = getCertifications();

  return (
    <section
      id="experience"
      aria-labelledby="experience-title"
      className="border-b border-line py-20 sm:py-24"
    >
      <Sheet>
        <SectionHeading
          index="03"
          label="Experience"
          id="experience-title"
          title="Timeline"
        >
          Roles, schools and certifications, newest first.
        </SectionHeading>

        <div className="border-t border-line">
          <ol aria-label="Roles">
            {experience.map((item, idx) => (
              <ExperienceRow key={item.id} item={item} index={idx} />
            ))}
          </ol>
        </div>

        <div className="mt-20 grid grid-cols-1 gap-16 lg:grid-cols-2 lg:gap-10">
          <div>
            <SubHeading label="Education" title="Where I learned the basics" />
            {education.length > 0 && (
              <ul className="grid grid-cols-1 border-l border-t border-line">
                {education.map((e) => (
                  <EducationCell key={e.id} item={e} />
                ))}
              </ul>
            )}
          </div>

          <div>
            <SubHeading label="Certifications" title="Credentials" />
            {certifications.length > 0 && (
              <table className="w-full border-t border-line-strong">
                <thead className="sr-only">
                  <tr>
                    <th scope="col">Certification</th>
                    <th scope="col">Issuer</th>
                    <th scope="col">Year</th>
                  </tr>
                </thead>
                <tbody>
                  {certifications.map((c) => (
                    <CertificationRow key={c.id} item={c} />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </Sheet>
    </section>
  );
};
