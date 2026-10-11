import React from 'react';
import * as SimpleIcons from 'react-icons/si';
import { useInViewReveal } from '../../hooks';
import { getSkills } from '../../content';
import type { Skill, SkillCategory, SkillTier } from '../../content';
import { MonoLabel, SectionHeading, Sheet } from '../drawing';

/** A skill's brand mark from Simple Icons, or its emoji fallback. */
const SkillIcon: React.FC<{ icon?: string | undefined; name: string }> = ({
  icon,
  name,
}) => {
  if (icon?.startsWith('si:')) {
    const key = icon.slice(3);
    const componentName =
      'Si' + key.charAt(0).toUpperCase() + key.slice(1).toLowerCase();
    const Logo = (
      SimpleIcons as Record<
        string,
        React.ComponentType<{ className?: string; 'aria-label'?: string }>
      >
    )[componentName];
    if (Logo) {
      return <Logo className="h-5 w-5 shrink-0 text-ink" aria-label={name} />;
    }
  }
  return (
    <span className="w-5 shrink-0 text-center text-base" aria-hidden="true">
      {icon ?? '💻'}
    </span>
  );
};

const CATEGORY_META: Record<SkillCategory, { label: string; code: string }> = {
  frontend: { label: 'Frontend', code: 'FE' },
  backend: { label: 'Backend', code: 'BE' },
  devops: { label: 'DevOps and infrastructure', code: 'OPS' },
  cloud: { label: 'Cloud platforms', code: 'CLD' },
  networking: { label: 'Networking and IT', code: 'NET' },
  other: { label: 'Other', code: 'OTH' },
};

const CATEGORY_ORDER: SkillCategory[] = [
  'frontend',
  'backend',
  'devops',
  'cloud',
  'networking',
  'other',
];

const TIER_META: Record<SkillTier, { label: string; description: string }> = {
  core: { label: 'Core', description: 'Use daily, deep knowledge' },
  working: { label: 'Working', description: 'Ship in it comfortably' },
  familiar: { label: 'Familiar', description: 'Can read and contribute' },
};

const TIER_ORDER: SkillTier[] = ['core', 'working', 'familiar'];

/** The tier mark: filled, half filled or outlined, like a drawing symbol. */
const TierGlyph: React.FC<{ tier: SkillTier; className?: string }> = ({
  tier,
  className = '',
}) => {
  const base = 'inline-block h-2.5 w-2.5 shrink-0 border border-accent';
  if (tier === 'core') {
    return (
      <span aria-hidden="true" className={`${base} bg-accent ${className}`} />
    );
  }
  if (tier === 'working') {
    return (
      <span
        aria-hidden="true"
        className={`${base} relative overflow-hidden ${className}`}
      >
        <span className="absolute inset-y-0 left-0 w-1/2 bg-accent" />
      </span>
    );
  }
  return <span aria-hidden="true" className={`${base} ${className}`} />;
};

/** One skill as a cell of the category's spec grid. */
const SkillCell: React.FC<{ skill: Skill }> = ({ skill }) => {
  const tierMeta = TIER_META[skill.tier];
  return (
    <li
      className="flex min-w-0 items-center gap-3 border-b border-r border-line px-3 py-3 transition-colors hover:bg-accent-soft"
      title={`${tierMeta.label}: ${tierMeta.description}`}
    >
      <SkillIcon icon={skill.icon} name={skill.name} />
      <span className="min-w-0 flex-1 truncate text-sm text-ink">
        {skill.name}
      </span>
      <TierGlyph tier={skill.tier} />
      <span className="sr-only">{tierMeta.label}</span>
    </li>
  );
};

/** The key to the tier marks. */
const TierLegend: React.FC = () => (
  <ul
    className="flex flex-wrap items-center gap-x-6 gap-y-2"
    aria-label="Tiers"
  >
    {TIER_ORDER.map((t) => {
      const m = TIER_META[t];
      return (
        <li key={t} className="flex items-center gap-2 text-sm">
          <TierGlyph tier={t} />
          <span className="font-medium text-ink">{m.label}</span>
          <span className="text-ink-muted">{m.description}</span>
        </li>
      );
    })}
  </ul>
);

const GRID =
  'grid grid-cols-1 border-l border-t border-line min-[420px]:grid-cols-2 md:grid-cols-3 lg:grid-cols-4';

/** The skills section, grouped by category and tier. */
export const Skills: React.FC = () => {
  const allSkills = getSkills();
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({
    threshold: 0.05,
  });

  const grouped = allSkills.reduce<Record<SkillCategory, Skill[]>>(
    (acc, skill) => {
      (acc[skill.category] = acc[skill.category] || []).push(skill);
      return acc;
    },
    {
      frontend: [],
      backend: [],
      devops: [],
      cloud: [],
      networking: [],
      other: [],
    }
  );

  return (
    <section
      id="skills"
      aria-labelledby="skills-title"
      className="border-b border-line py-20 sm:py-28"
    >
      <Sheet>
        <div
          ref={ref}
          className={
            isInView ? 'motion-safe:animate-fade-in' : 'motion-safe:opacity-0'
          }
        >
          <SectionHeading
            index="03"
            label="Skills"
            id="skills-title"
            title="Tools I work with"
          >
            A snapshot of my current toolkit across frontend, backend, infra,
            and the rest.
          </SectionHeading>

          <div className="-mt-4 mb-10 border-y border-line py-3">
            <TierLegend />
          </div>

          <div className="space-y-10">
            {CATEGORY_ORDER.map((cat) => {
              const skills = grouped[cat];
              if (!skills || skills.length === 0) return null;
              const meta = CATEGORY_META[cat];
              return (
                <div key={cat}>
                  <div className="mb-3 flex items-baseline gap-3">
                    <span className="font-mono text-xs text-accent">
                      {meta.code}
                    </span>
                    <h3 className="text-base font-semibold text-ink">
                      {meta.label}
                    </h3>
                    <span
                      className="h-px flex-1 self-center bg-line"
                      aria-hidden="true"
                    />
                    <MonoLabel>
                      {String(skills.length).padStart(2, '0')} items
                    </MonoLabel>
                  </div>
                  <ul className={GRID}>
                    {skills.map((skill) => (
                      <SkillCell key={skill.id} skill={skill} />
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      </Sheet>
    </section>
  );
};
