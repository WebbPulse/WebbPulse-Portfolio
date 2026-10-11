import { StrictMode } from 'react';
import { createRoot, hydrateRoot } from 'react-dom/client';
import App from './App.tsx';

/** A pathname without its trailing slash, keeping the root as `/`. */
const normalise = (path: string): string =>
  path.length > 1 ? path.replace(/\/+$/, '') || '/' : path;

const container = document.getElementById('root')!;
const app = (
  <StrictMode>
    <App />
  </StrictMode>
);

if (
  container.dataset.prerendered !== undefined &&
  normalise(container.dataset.prerendered) ===
    normalise(window.location.pathname)
) {
  hydrateRoot(container, app);
} else {
  container.replaceChildren();
  createRoot(container).render(app);
}
