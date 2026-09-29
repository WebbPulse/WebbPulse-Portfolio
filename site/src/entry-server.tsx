import { StrictMode } from 'react';
import { renderToString } from 'react-dom/server';
import App from './App';

/** Render the page to static HTML for the build-time prerender. */
export function render(): string {
  return renderToString(
    <StrictMode>
      <App />
    </StrictMode>
  );
}
