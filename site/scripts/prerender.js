/**
 * Render the page to HTML at build time and write it into dist/index.html.
 * The page has no interactive parts, so the client bundle is dropped and the
 * stylesheet is inlined: the site ships as one HTML file plus static assets.
 */
import { readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const dist = `${root}dist`;
const ssrDir = `${root}dist-ssr`;
const indexPath = `${dist}/index.html`;
const placeholder = '<div id="root"></div>';
const scriptTag = /\s*<script type="module"[^>]*><\/script>/g;
const stylesheetTag =
  /<link rel="stylesheet"[^>]*href="\/(assets\/[^"]+\.css)"[^>]*>/g;

const { render } = await import(`${ssrDir}/entry-server.js`);
const template = await readFile(indexPath, 'utf8');

if (!template.includes(placeholder)) {
  throw new Error(`dist/index.html has no ${placeholder} to fill`);
}

const stylesheets = [...template.matchAll(stylesheetTag)];
let html = template.replace(scriptTag, '');
for (const [tag, path] of stylesheets) {
  const css = await readFile(`${dist}/${path}`, 'utf8');
  html = html.replace(tag, () => `<style>${css.trim()}</style>`);
}
html = html.replace(placeholder, () => `<div id="root">${render()}</div>`);

if (html.includes('<script') || html.includes('rel="stylesheet"')) {
  throw new Error(
    'dist/index.html still references a bundle after prerendering'
  );
}

await writeFile(indexPath, html);
for (const name of await readdir(`${dist}/assets`)) {
  if (name.endsWith('.js') || name.endsWith('.css')) {
    await rm(`${dist}/assets/${name}`);
  }
}
if ((await readdir(`${dist}/assets`)).length === 0) {
  await rm(`${dist}/assets`, { recursive: true });
}
await rm(ssrDir, { recursive: true, force: true });
console.log('Prerendered dist/index.html');
