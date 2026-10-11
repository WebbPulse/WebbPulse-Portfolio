import React from 'react';
import { useInViewReveal } from '../../hooks';
import { getSiteContent } from '../../content';
import {
  DimensionLine,
  MonoLabel,
  RegistrationMarks,
  Sheet,
  TitleBlock,
} from '../drawing';

/** One labelled box of the schematic. */
const Node: React.FC<{
  x: number;
  y: number;
  w: number;
  label: string;
  sub?: string;
}> = ({ x, y, w, label, sub }) => (
  <g>
    <rect
      x={x}
      y={y}
      width={w}
      height={sub ? 44 : 32}
      fill="var(--cp-paper-raised)"
      stroke="currentColor"
      strokeWidth="1"
    />
    <text
      x={x + 10}
      y={y + 20}
      className="fill-ink font-mono"
      fontSize="11"
      letterSpacing="0.04em"
    >
      {label}
    </text>
    {sub && (
      <text
        x={x + 10}
        y={y + 35}
        className="fill-ink-muted font-mono"
        fontSize="9.5"
      >
        {sub}
      </text>
    )}
  </g>
);

/**
 * A static line drawing of how this site is served, standing in for the live
 * system map that replaces it.
 */
const Schematic: React.FC = () => (
  <svg
    viewBox="0 0 560 310"
    className="h-auto w-full text-line-strong"
    role="img"
    aria-labelledby="schematic-title"
  >
    <title id="schematic-title">
      Request path: browser to CloudFront and S3 for the page, and to API
      Gateway, four Lambda functions and DynamoDB for data
    </title>
    <defs>
      <marker
        id="arrow"
        viewBox="0 0 8 8"
        refX="7"
        refY="4"
        markerWidth="7"
        markerHeight="7"
        orient="auto-start-reverse"
      >
        <path d="M0 0 8 4 0 8" fill="none" stroke="currentColor" />
      </marker>
    </defs>
    <g fill="none" stroke="currentColor" strokeWidth="1">
      <path d="M96 76h46" markerEnd="url(#arrow)" />
      <path d="M244 76h50" markerEnd="url(#arrow)" />
      <path d="M60 92v102h82" markerEnd="url(#arrow)" />
      <path d="M244 194h36" />
      <path d="M280 144v120" />
      <path d="M280 144h14" markerEnd="url(#arrow)" />
      <path d="M280 184h14" markerEnd="url(#arrow)" />
      <path d="M280 224h14" markerEnd="url(#arrow)" />
      <path d="M280 264h14" markerEnd="url(#arrow)" />
      <path d="M396 144h28M396 184h28M396 224h28M396 264h28" />
      <path d="M424 144v120" />
      <path d="M424 204h34" markerEnd="url(#arrow)" />
      <path d="M20 22h520" strokeDasharray="2 4" />
    </g>
    <Node x={24} y={60} w={72} label="browser" />
    <Node x={144} y={54} w={100} label="cloudfront" sub="cdn, tls" />
    <Node x={296} y={54} w={100} label="s3" sub="static bundle" />
    <Node x={144} y={172} w={100} label="api gateway" sub="http api" />
    <Node x={296} y={128} w={100} label="content" />
    <Node x={296} y={168} w={100} label="resume" />
    <Node x={296} y={208} w={100} label="identity" />
    <Node x={296} y={248} w={100} label="public" />
    <Node x={460} y={182} w={84} label="dynamodb" sub="tables" />
    <text
      x="322"
      y="300"
      className="fill-ink-muted font-mono"
      fontSize="9"
      letterSpacing="0.08em"
    >
      LAMBDA x4
    </text>
    <text
      x="20"
      y="12"
      className="fill-ink-muted font-mono"
      fontSize="9"
      letterSpacing="0.08em"
    >
      FIG. 1 / REQUEST PATH
    </text>
  </svg>
);

/**
 * The landing sheet: name, role and summary from site content beside a framed
 * schematic of the system. The schematic is a holding drawing for the live
 * system map.
 */
const Hero: React.FC = () => {
  const content = getSiteContent();
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({ threshold: 0.1 });

  return (
    <section
      id="hero"
      aria-labelledby="hero-title"
      className="relative border-b border-line"
    >
      <Sheet className="py-14 sm:py-20 lg:py-24">
        <div
          ref={ref}
          className={`grid items-center gap-12 lg:grid-cols-12 lg:gap-10 ${isInView ? 'motion-safe:animate-fade-in-up' : 'motion-safe:opacity-0'}`}
        >
          <div className="lg:col-span-6">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-accent">01</span>
              <span className="h-3 w-px bg-line-strong" aria-hidden="true" />
              <MonoLabel>{content.hero_subtitle}</MonoLabel>
            </div>

            <h1
              id="hero-title"
              className="mt-6 text-5xl sm:text-6xl lg:text-7xl font-semibold leading-[1.02] tracking-[-0.03em] text-ink"
            >
              {content.hero_title}
            </h1>

            <p className="mt-6 max-w-xl text-lg sm:text-xl leading-relaxed text-ink-muted">
              {content.hero_description}
            </p>

            <div className="mt-10 flex flex-col gap-3 sm:flex-row">
              <a
                href="#projects"
                className="group inline-flex items-center justify-center gap-2 border border-ink bg-ink px-5 py-3 text-sm font-medium text-paper transition-colors hover:bg-accent hover:border-accent"
              >
                View my work
                <span
                  aria-hidden="true"
                  className="font-mono transition-transform motion-safe:group-hover:translate-x-0.5"
                >
                  →
                </span>
              </a>
              <a
                href="#contact"
                className="inline-flex items-center justify-center border border-line-strong px-5 py-3 text-sm font-medium text-ink transition-colors hover:border-ink"
              >
                Get in touch
              </a>
            </div>
          </div>

          <div className="lg:col-span-6">
            <figure className="relative border border-line bg-paper-raised/70 p-4 sm:p-6">
              <RegistrationMarks />
              <Schematic />
              <figcaption className="mt-4">
                <DimensionLine label="portfolio.webbpulse.com" />
              </figcaption>
            </figure>
            <TitleBlock
              className="mt-6"
              columns={3}
              rows={[
                { label: 'Role', value: content.hero_subtitle },
                { label: 'Stack', value: 'React, FastAPI' },
                { label: 'Runs on', value: 'AWS Lambda' },
              ]}
            />
          </div>
        </div>
      </Sheet>
    </section>
  );
};

export default Hero;
