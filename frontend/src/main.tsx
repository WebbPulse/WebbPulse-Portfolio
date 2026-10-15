import { StrictMode } from 'react';
import { createRoot, hydrateRoot } from 'react-dom/client';
import App from './App.tsx';
import { preloadPageFor } from './routing/pages';

/** A pathname without its trailing slash, keeping the root as `/`. */
const normalise = (path: string): string =>
  path.length > 1 ? path.replace(/\/+$/, '') || '/' : path;

const container = document.getElementById('root')!;
const prerendered = container.dataset['prerendered'];
const app = (
  <StrictMode>
    <App />
  </StrictMode>
);

/** Hydrates the prerendered markup, or renders fresh when there is none. */
function start(): void {
  if (
    prerendered !== undefined &&
    normalise(prerendered) === normalise(window.location.pathname)
  ) {
    hydrateRoot(container, app);
  } else {
    container.replaceChildren();
    createRoot(container).render(app);
  }
}

preloadPageFor(window.location.pathname).then(start, start);
