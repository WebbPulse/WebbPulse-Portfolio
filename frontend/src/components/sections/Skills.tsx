import React from 'react';
import * as SimpleIcons from 'react-icons/si';
import { GradientText } from '../common';
import { useSkills, useInViewReveal } from '../../hooks';
import type { Skill, SkillCategory, SkillTier } from '../../services/api';

// `icon` is a free-form string. Strings that start with `si:` resolve to a
// Simple Icons brand logo from react-icons (e.g. `si:react` → SiReact). Anything
// else (emoji, plain text) renders as-is so soft skills without a brand logo
// keep their emoji.
const SkillIcon: React.FC<{ icon?: string; name: string }> = ({
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
      return <Logo className="w-8 h-8 text-surface-100" aria-label={name} />;
    }
  }
  return (
    <span className="text-3xl" aria-hidden="true">
      {icon ?? '💻'}
    </span>
  );
};

const CATEGORY_META: Record<
  SkillCategory,
  { label: string; accent: string; glow: string }
> = {
  frontend: {
    label: 'Frontend',
    accent: 'text-accent-cyan-400',
    glow: 'hover:shadow-glow-cyan',
  },
  backend: {
    label: 'Backend',
    accent: 'text-accent-violet-400',
    glow: 'hover:shadow-glow-violet',
  },
  devops: {
    label: 'DevOps & Infrastructure',
    accent: 'text-accent-fuchsia-400',
    glow: 'hover:shadow-glow-fuchsia',
  },
  cloud: {
    label: 'Cloud Platforms',
    accent: 'text-accent-cyan-400',
    glow: 'hover:shadow-glow-cyan',
  },
  networking: {
    label: 'Networking & IT',
    accent: 'text-accent-violet-300',
    glow: 'hover:shadow-glow-violet',
  },
  other: {
    label: 'Other',
    accent: 'text-surface-200',
    glow: 'hover:shadow-glow-soft',
  },
};

const CATEGORY_ORDER: SkillCategory[] = [
  'frontend',
  'backend',
  'devops',
  'cloud',
  'networking',
  'other',
];

const TIER_META: Record<
  SkillTier,
  { label: string; description: string; accent: string }
> = {
  core: {
    label: 'Core',
    description: 'Use daily, deep knowledge',
    accent: 'text-accent-cyan-400',
  },
  working: {
    label: 'Working',
    description: 'Ship in it comfortably',
    accent: 'text-accent-violet-300',
  },
  familiar: {
    label: 'Familiar',
    description: 'Can read and contribute',
    accent: 'text-surface-400',
  },
};

const TIER_ORDER: SkillTier[] = ['core', 'working', 'familiar'];

const TierGlyph: React.FC<{ tier: SkillTier; className?: string }> = ({
  tier,
  className = '',
}) => {
  // Filled / half / outline circle, color-coded
  const base = 'inline-block w-3 h-3 rounded-full border';
  if (tier === 'core') {
    return (
      <span
        aria-hidden="true"
        className={`${base} bg-accent-cyan-400 border-accent-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.6)] ${className}`}
      />
    );
  }
  if (tier === 'working') {
    return (
      <span
        aria-hidden="true"
        className={`${base} relative overflow-hidden border-accent-violet-300 ${className}`}
      >
        <span className="absolute inset-y-0 left-0 w-1/2 bg-accent-violet-300" />
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`${base} border-surface-400 ${className}`}
    />
  );
};

const SkillCard: React.FC<{ skill: Skill; index: number }> = ({
  skill,
  index,
}) => {
  const meta = CATEGORY_META[skill.category];
  const tierMeta = TIER_META[skill.tier];
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({ threshold: 0.2 });

  return (
    <div
      ref={ref}
      style={{ animationDelay: `${(index % 8) * 60}ms` }}
      className={`group relative surface-glass rounded-2xl p-5 transition-all duration-500 hover:-translate-y-1 ${meta.glow} ${isInView ? 'animate-fade-in-up' : 'opacity-0'}`}
      title={`${tierMeta.label} — ${tierMeta.description}`}
    >
      <div className="flex items-start justify-between">
        <SkillIcon icon={skill.icon} name={skill.name} />
        <span
          className={`flex items-center gap-1.5 text-[11px] uppercase tracking-[0.14em] font-medium ${tierMeta.accent}`}
        >
          <TierGlyph tier={skill.tier} />
          {tierMeta.label}
        </span>
      </div>
      <h4 className="mt-4 font-display font-semibold text-surface-50 text-base">
        {skill.name}
      </h4>
    </div>
  );
};

const SkillSkeletonCard: React.FC = () => (
  <div className="surface-glass rounded-2xl p-5 animate-pulse">
    <div className="flex items-center justify-between">
      <div className="w-8 h-8 bg-surface-800 rounded" />
      <div className="w-16 h-3 bg-surface-800 rounded" />
    </div>
    <div className="mt-4 h-4 bg-surface-800 rounded w-2/3" />
  </div>
);

const TierLegend: React.FC = () => (
  <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-surface-300">
    {TIER_ORDER.map(t => {
      const m = TIER_META[t];
      return (
        <span key={t} className="flex items-center gap-2">
          <TierGlyph tier={t} />
          <span className={`font-medium ${m.accent}`}>{m.label}</span>
          <span className="text-surface-500">{m.description}</span>
        </span>
      );
    })}
  </div>
);

export const Skills: React.FC = () => {
  const { data, loading, error } = useSkills();
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({
    threshold: 0.05,
  });

  const grouped = (data ?? []).reduce<Record<SkillCategory, Skill[]>>(
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
      className="relative py-24 sm:py-32 overflow-hidden bg-surface-950"
    >
      <div className="absolute inset-0 bg-mesh-1 opacity-40 pointer-events-none" />
      <div
        ref={ref}
        className={`relative z-10 max-w-7xl mx-auto px-6 sm:px-8 ${isInView ? 'animate-fade-in' : 'opacity-0'}`}
      >
        <div className="text-center mb-10 max-w-2xl mx-auto">
          <span className="inline-block text-xs uppercase tracking-[0.2em] text-accent-violet-400 mb-4">
            Skills
          </span>
          <h2 className="font-display text-4xl sm:text-5xl font-bold text-surface-50 mb-4">
            Tools I <GradientText as="span">work with</GradientText>
          </h2>
          <p className="text-surface-300 text-lg">
            A snapshot of my current toolkit across frontend, backend, infra,
            and the rest.
          </p>
        </div>

        <div className="mb-12">
          <TierLegend />
        </div>

        {loading && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <SkillSkeletonCard key={i} />
            ))}
          </div>
        )}

        {error && !loading && (
          <p className="text-center text-surface-400">
            Couldn't load skills right now.
          </p>
        )}

        {!loading && !error && (
          <div className="space-y-14">
            {CATEGORY_ORDER.map(cat => {
              const skills = grouped[cat];
              if (!skills || skills.length === 0) return null;
              const meta = CATEGORY_META[cat];
              return (
                <div key={cat}>
                  <div className="flex items-center gap-3 mb-6">
                    <span
                      className={`text-xs uppercase tracking-[0.2em] font-medium ${meta.accent}`}
                    >
                      {meta.label}
                    </span>
                    <span className="flex-1 h-px bg-gradient-to-r from-surface-700 to-transparent" />
                    <span className="text-xs text-surface-500">
                      {skills.length}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                    {skills.map((skill, idx) => (
                      <SkillCard key={skill.id} skill={skill} index={idx} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
};
