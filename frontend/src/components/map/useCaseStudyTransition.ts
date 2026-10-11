import type React from 'react';
import { useCallback } from 'react';
import { flushSync } from 'react-dom';
import { useNavigate } from 'react-router-dom';

/** The view transition name the clicked node and the case study header share. */
export const CASE_STUDY_TRANSITION_NAME = 'case-study-head';

/** The selector for the case study header the transition morphs into. */
const HEADER_SELECTOR = '[data-case-study-head]';

/** A document that may or may not support view transitions. */
type TransitionDocument = Document & {
  startViewTransition?: (update: () => Promise<void>) => unknown;
};

/** Resolves once `selector` matches, or after `timeoutMs` either way. */
function waitForElement(selector: string, timeoutMs: number): Promise<void> {
  return new Promise((resolve) => {
    const started = performance.now();
    const check = () => {
      if (
        document.querySelector(selector) ||
        performance.now() - started > timeoutMs
      ) {
        resolve();
        return;
      }
      requestAnimationFrame(check);
    };
    check();
  });
}

/** True for a click that should open a link in place, not a new tab. */
function isPlainClick(event: React.MouseEvent): boolean {
  return (
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  );
}

/**
 * A click handler that morphs a map node into the case study header.
 *
 * It only takes over when the browser supports view transitions, motion is
 * allowed and the click is a plain one. Otherwise the link navigates as usual.
 */
export function useCaseStudyTransition(
  reduced: boolean
): (event: React.MouseEvent<HTMLElement>, href: string) => void {
  const navigate = useNavigate();
  return useCallback(
    (event: React.MouseEvent<HTMLElement>, href: string) => {
      const doc = document as TransitionDocument;
      if (
        reduced ||
        typeof doc.startViewTransition !== 'function' ||
        !isPlainClick(event)
      ) {
        return;
      }
      event.preventDefault();
      const source = event.currentTarget;
      source.style.setProperty(
        'view-transition-name',
        CASE_STUDY_TRANSITION_NAME
      );
      doc.startViewTransition(async () => {
        source.style.removeProperty('view-transition-name');
        flushSync(() => {
          void navigate(href);
        });
        await waitForElement(HEADER_SELECTOR, 500);
      });
    },
    [navigate, reduced]
  );
}
