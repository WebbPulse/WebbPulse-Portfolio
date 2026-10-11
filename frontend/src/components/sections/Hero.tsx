import React from 'react';
import { getExperience } from '../../content';
import { useLiveFigures } from '../../hooks/useLiveFigures';
import { MonoLabel, Sheet } from '../drawing';
import { FiguresStrip, SystemMap } from '../map';

/** The current role as one line, such as `Software Engineer, WebbPulse`. */
const currentRole = (): string => {
  const latest = getExperience().find((entry) => !entry.end_date);
  return latest ? `${latest.title}, ${latest.company}` : 'Software Engineer';
};

/**
 * The landing sheet: name, current role and the live system map of the
 * WebbPulse estate, with the live figures strip when the API answers.
 */
const Hero: React.FC = () => {
  const figures = useLiveFigures();

  return (
    <section
      id="map"
      aria-labelledby="hero-title"
      className="relative border-b border-line"
    >
      <Sheet className="py-12 sm:py-16 lg:py-20">
        <div className="max-w-3xl">
          <div>
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-accent">01</span>
              <span className="h-3 w-px bg-line-strong" aria-hidden="true" />
              <MonoLabel>{currentRole()}</MonoLabel>
            </div>
            <h1
              id="hero-title"
              className="mt-5 text-5xl font-semibold leading-[1.02] tracking-[-0.03em] text-ink sm:text-6xl"
            >
              Tyler Webb
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-muted">
              I build and run four products on shared Python, TypeScript and
              Terraform packages, deployed into one AWS organisation by a
              Terraform control plane I wrote. This is the map of how they
              connect.
            </p>
          </div>
        </div>

        <figure className="mt-12">
          <SystemMap figures={figures} />
          <figcaption className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3">
            <MonoLabel>Fig. 1 / The WebbPulse estate</MonoLabel>
            <span className="hidden font-mono text-[0.6875rem] text-ink-faint lg:inline">
              Hover or tab through a node to trace its connections
            </span>
          </figcaption>
        </figure>
        <FiguresStrip figures={figures} />
      </Sheet>
    </section>
  );
};

export default Hero;
