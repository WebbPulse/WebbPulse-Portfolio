import React from 'react';
import { AnimatedOrb, GradientText } from '../common';
import {
  useSiteContent,
  useInViewReveal,
  useScrollParallax,
} from '../../hooks';

const FALLBACK = {
  hero_title: "Hi, I'm Tyler Webb",
  hero_subtitle: 'Software Engineer',
  hero_description: 'Software engineer building privacy-conscious systems.',
};

/** The landing hero, over site content with a static fallback. */
const Hero: React.FC = () => {
  const { data, loading } = useSiteContent();
  const parallaxFast = useScrollParallax(0.35);
  const parallaxSlow = useScrollParallax(0.18);
  const { ref, isInView } = useInViewReveal<HTMLDivElement>({ threshold: 0.1 });

  const content = data ?? FALLBACK;

  return (
    <section
      id="hero"
      className="relative min-h-[100svh] flex items-center justify-center overflow-hidden bg-surface-950"
    >
      <div
        className="absolute inset-0 bg-mesh-1 pointer-events-none"
        aria-hidden="true"
      />

      <AnimatedOrb
        gradient="from-accent-cyan-500 to-accent-cyan-400"
        size="w-[32rem] h-[32rem]"
        position="-top-32 -left-32"
        variant={1}
        parallaxY={-parallaxSlow}
        opacity="opacity-40"
      />
      <AnimatedOrb
        gradient="from-accent-violet-500 to-accent-fuchsia-500"
        size="w-[36rem] h-[36rem]"
        position="-bottom-40 -right-32"
        variant={2}
        parallaxY={parallaxFast}
        opacity="opacity-35"
      />
      <AnimatedOrb
        gradient="from-accent-fuchsia-400 to-accent-violet-500"
        size="w-[24rem] h-[24rem]"
        position="top-1/3 left-1/2"
        variant={3}
        parallaxY={-parallaxFast * 0.5}
        opacity="opacity-20"
      />

      <div
        ref={ref}
        className={`relative z-10 max-w-5xl mx-auto px-6 sm:px-8 text-center ${isInView ? 'animate-fade-in-up' : 'opacity-0'}`}
      >
        <span className="inline-flex items-center gap-2 px-4 py-1.5 mb-8 text-xs uppercase tracking-[0.18em] font-medium text-surface-300 surface-glass rounded-full">
          <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan-400 animate-pulse" />
          {loading ? 'Loading…' : content.hero_subtitle}
        </span>

        <h1 className="font-display text-5xl sm:text-6xl md:text-7xl lg:text-8xl font-bold tracking-tight text-surface-50 leading-[1.05]">
          {content.hero_title.split(' ').map((word, i, arr) => {
            const isLast = i === arr.length - 1;
            return isLast ? (
              <GradientText key={i} as="span" animated>
                {word}
              </GradientText>
            ) : (
              <span key={i}>{word} </span>
            );
          })}
        </h1>

        <p className="mt-8 text-lg sm:text-xl text-surface-300 max-w-2xl mx-auto leading-relaxed">
          {content.hero_description}
        </p>

        <div className="mt-12 flex flex-col sm:flex-row gap-4 justify-center items-center">
          <a
            href="#projects"
            onClick={(e) => {
              e.preventDefault();
              document
                .querySelector('#projects')
                ?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="group relative inline-flex items-center justify-center px-8 py-3.5 rounded-full font-medium text-surface-50 bg-gradient-accent shadow-glow-violet hover:shadow-glow-fuchsia transition-shadow duration-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-fuchsia-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-950"
            style={{ backgroundSize: '200% 200%' }}
          >
            <span className="relative z-10">View My Work</span>
            <span className="ml-2 transition-transform duration-300 group-hover:translate-x-1">
              →
            </span>
          </a>
          <a
            href="#contact"
            onClick={(e) => {
              e.preventDefault();
              document
                .querySelector('#contact')
                ?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="inline-flex items-center justify-center px-8 py-3.5 rounded-full font-medium text-surface-100 surface-glass surface-glass-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-950"
          >
            Get In Touch
          </a>
        </div>
      </div>

      <button
        type="button"
        onClick={() =>
          document
            .querySelector('#about')
            ?.scrollIntoView({ behavior: 'smooth' })
        }
        aria-label="Scroll to next section"
        className="absolute bottom-8 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-2 text-surface-400 hover:text-surface-200 transition-colors group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-950 rounded-full p-2"
      >
        <span className="text-xs uppercase tracking-[0.2em]">Scroll</span>
        <span className="w-px h-10 bg-gradient-to-b from-surface-400 to-transparent group-hover:from-accent-cyan-400" />
      </button>
    </section>
  );
};

export default Hero;
