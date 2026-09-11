import { useEffect, useState } from 'react';
import { useReducedMotion } from './useReducedMotion';

/**
 * Counts from 0 up to `target` once `start` becomes true. RAF-driven.
 * Snaps to target immediately under prefers-reduced-motion.
 */
export function useCountUp(target: number, start: boolean, durationMs = 1200) {
  const reducedMotion = useReducedMotion();
  const [value, setValue] = useState(start && reducedMotion ? target : 0);

  useEffect(() => {
    if (!start) return;
    if (reducedMotion) {
      setValue(target);
      return;
    }
    let raf = 0;
    const begin = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - begin) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(target * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, start, durationMs, reducedMotion]);

  return value;
}
