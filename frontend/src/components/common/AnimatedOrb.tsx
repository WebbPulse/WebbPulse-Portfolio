import React from 'react';

interface AnimatedOrbProps {
  /** Tailwind color classes for the orb's gradient (e.g., "from-accent-cyan-500 to-accent-violet-500") */
  gradient?: string;
  /** Tailwind size classes (e.g., "w-72 h-72") */
  size?: string;
  /** Tailwind position classes (e.g., "-top-20 -left-20") */
  position?: string;
  /** Animation: 'blob-1' | 'blob-2' | 'blob-3' */
  variant?: 1 | 2 | 3;
  /** Optional inline transform (use for parallax offsets) */
  parallaxY?: number;
  /** Tailwind opacity class */
  opacity?: string;
}

const VARIANT_CLASS = {
  1: 'animate-blob-1',
  2: 'animate-blob-2',
  3: 'animate-blob-3',
} as const;

/** A decorative gradient orb, held still under reduced motion. */
const AnimatedOrb: React.FC<AnimatedOrbProps> = ({
  gradient = 'from-accent-violet-500 to-accent-cyan-500',
  size = 'w-[28rem] h-[28rem]',
  position = 'top-0 left-0',
  variant = 1,
  parallaxY = 0,
  opacity = 'opacity-30',
}) => {
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute ${position} ${size} ${opacity} ${VARIANT_CLASS[variant]}`}
      style={{
        transform: parallaxY ? `translate3d(0, ${parallaxY}px, 0)` : undefined,
        willChange: 'transform',
      }}
    >
      <div
        className={`w-full h-full rounded-full bg-gradient-to-br ${gradient} blur-3xl`}
      />
    </div>
  );
};

export default AnimatedOrb;
