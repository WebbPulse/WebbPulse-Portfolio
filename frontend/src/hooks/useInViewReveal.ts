import { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from './useReducedMotion';

interface Options {
  threshold?: number;
  rootMargin?: string;
}

/** Where a revealing element is: as rendered, waiting below the fold, or revealed. */
type RevealState = 'static' | 'hidden' | 'revealed';

const REVEAL_CLASS: Record<RevealState, string> = {
  static: '',
  hidden: 'motion-safe:opacity-0',
  revealed: 'motion-safe:animate-fade-in-up',
};

/**
 * Scroll reveal for an element below the fold.
 *
 * The prerendered markup and the hydrating render leave the element visible,
 * so it shows without JS. After hydration, and only when motion is allowed,
 * an element that starts below the viewport is hidden and fades in once it
 * scrolls into view. Anything already on screen stays as it is.
 */
export function useInViewReveal<T extends HTMLElement = HTMLDivElement>({
  threshold = 0.15,
  rootMargin = '0px 0px -10% 0px',
}: Options = {}) {
  const ref = useRef<T | null>(null);
  const reducedMotion = useReducedMotion();
  const [state, setState] = useState<RevealState>('static');

  useEffect(() => {
    const node = ref.current;
    if (reducedMotion || !node || typeof IntersectionObserver === 'undefined') {
      return;
    }

    let first = true;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const below = entry.boundingClientRect.top >= window.innerHeight;
          if (entry.isIntersecting) {
            setState((current) =>
              current === 'hidden' ? 'revealed' : current
            );
            observer.disconnect();
          } else if (first && !below) {
            observer.disconnect();
          } else if (first) {
            setState('hidden');
          }
          first = false;
        }
      },
      { threshold, rootMargin }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [threshold, rootMargin, reducedMotion]);

  return { ref, revealClass: reducedMotion ? '' : REVEAL_CLASS[state] };
}
