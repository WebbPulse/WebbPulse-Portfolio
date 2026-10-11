import React from 'react';
import { getSkills } from '../../content';
import type { Skill, SkillCategory, SkillTier } from '../../content';
import { SectionHeading, Sheet } from '../drawing';

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

/** One skill as an inline entry with its tier mark. */
const SkillItem: React.FC<{ skill: Skill }> = ({ skill }) => {
  const tierMeta = TIER_META[skill.tier];
  return (
    <li
      className="inline-flex items-center gap-1.5 text-sm text-ink"
      title={`${tierMeta.label}: ${tierMeta.description}`}
    >
      <TierGlyph tier={skill.tier} />
      <span>{skill.name}</span>
      <span className="sr-only">, {tierMeta.label}</span>
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
        <li key={t} className="flex items-center gap-2 text-xs">
          <TierGlyph tier={t} />
          <span className="font-medium text-ink">{m.label}</span>
          <span className="text-ink-muted">{m.description}</span>
        </li>
      );
    })}
  </ul>
);

/** The skills, one compact row per category with tier marks. */
export const Skills: React.FC = () => {
  const allSkills = getSkills();
  const grouped = new Map<SkillCategory, Skill[]>();
  for (const skill of allSkills) {
    grouped.set(skill.category, [
      ...(grouped.get(skill.category) ?? []),
      skill,
    ]);
  }

  return (
    <section
      id="skills"
      aria-labelledby="skills-title"
      className="border-b border-line py-20 sm:py-24"
    >
      <Sheet>
        <SectionHeading
          index="04"
          label="Skills"
          id="skills-title"
          title="Tools"
          aside={<TierLegend />}
        />
        <dl className="border-t border-line">
          {CATEGORY_ORDER.map((cat) => {
            const skills = grouped.get(cat);
            if (!skills?.length) return null;
            const meta = CATEGORY_META[cat];
            return (
              <div
                key={cat}
                className="grid gap-2 border-b border-line py-4 md:grid-cols-[12rem_minmax(0,1fr)] md:gap-8"
              >
                <dt className="flex items-baseline gap-3">
                  <span className="font-mono text-xs text-accent">
                    {meta.code}
                  </span>
                  <span className="text-sm font-semibold text-ink">
                    {meta.label}
                  </span>
                </dt>
                <dd>
                  <ul className="flex flex-wrap gap-x-5 gap-y-2">
                    {skills.map((skill) => (
                      <SkillItem key={skill.id} skill={skill} />
                    ))}
                  </ul>
                </dd>
              </div>
            );
          })}
        </dl>
      </Sheet>
    </section>
  );
};
