import { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from './useReducedMotion';

interface Options {
  threshold?: number;
  rootMargin?: string;
  /** Re-fire on every entry/exit instead of single-shot. */
  repeat?: boolean;
}

/**
 * IntersectionObserver reveal hook.
 *
 * Returns a ref to attach and a flag that flips once the element scrolls into
 * view. Single-fire by default, and immediately true under reduced motion.
 */
export function useInViewReveal<T extends HTMLElement = HTMLDivElement>({
  threshold = 0.15,
  rootMargin = '0px 0px -10% 0px',
  repeat = false,
}: Options = {}) {
  const ref = useRef<T | null>(null);
  const reducedMotion = useReducedMotion();
  const [isInView, setIsInView] = useState<boolean>(reducedMotion);

  useEffect(() => {
    if (reducedMotion) {
      setIsInView(true);
      return;
    }
    const node = ref.current;
    if (!node) return;
    if (typeof IntersectionObserver === 'undefined') {
      setIsInView(true);
      return;
    }

    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            setIsInView(true);
            if (!repeat) observer.unobserve(entry.target);
          } else if (repeat) {
            setIsInView(false);
          }
        });
      },
      { threshold, rootMargin }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [threshold, rootMargin, repeat, reducedMotion]);

  return { ref, isInView };
}
