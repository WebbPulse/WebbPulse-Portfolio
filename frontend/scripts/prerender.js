/**
 * Prerender every public route into dist at build time.
 *
 * Each route gets its own index.html with the page markup in the root and its
 * own title, description, canonical, Open Graph and Twitter tags in the head.
 * The client bundle stays, and main.tsx hydrates the markup. The not found
 * page goes to dist/404.html, a sitemap.xml lists the rest and robots.txt
 * points at the sitemap. A route served by a split page gets modulepreload
 * links for that page's chunks, read from the Vite manifest, so hydration does
 * not wait on a second round trip.
 */
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const dist = `${root}dist`;
const ssrDir = `${root}dist-ssr`;
const indexPath = `${dist}/index.html`;
const placeholder = '<div id="root"></div>';
const headRegion = /<!-- page-meta -->[\s\S]*?<!-- \/page-meta -->/;
const manifestDir = `${dist}/.vite`;
const manifest = JSON.parse(
  await readFile(`${manifestDir}/manifest.json`, 'utf8')
);

const entry = await import(`${ssrDir}/entry-server.js`);
const {
  render,
  preloadPages,
  prerenderRoutes,
  pageSourceFor,
  NOT_FOUND_PATH,
  SITE_ORIGIN,
} = entry;
await preloadPages();
const template = await readFile(indexPath, 'utf8');

if (!template.includes(placeholder)) {
  throw new Error(`dist/index.html has no ${placeholder} to fill`);
}
if (!headRegion.test(template)) {
  throw new Error('dist/index.html has no page-meta region in its head');
}

/** Escapes text for an HTML attribute or element body. */
const escape = (text) =>
  text
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

/** The canonical URL of a route. */
const urlFor = (path) => `${SITE_ORIGIN}${path}`;

/** The head tags for one page. */
function headTags(path, meta) {
  const title = escape(meta.title);
  const description = escape(meta.description);
  const article = path.startsWith('/work/') || path.startsWith('/blog/');
  const tags = [
    `<title>${title}</title>`,
    `<meta name="description" content="${description}" />`,
    meta.noindex
      ? '<meta name="robots" content="noindex" />'
      : `<link rel="canonical" href="${escape(urlFor(path))}" />`,
    `<meta property="og:type" content="${article ? 'article' : 'website'}" />`,
    '<meta property="og:site_name" content="Tyler Webb" />',
    `<meta property="og:title" content="${title}" />`,
    `<meta property="og:description" content="${description}" />`,
    `<meta property="og:url" content="${escape(urlFor(path))}" />`,
    `<meta property="og:image" content="${escape(urlFor('/headshot.jpg'))}" />`,
    '<meta name="twitter:card" content="summary" />',
    `<meta name="twitter:title" content="${title}" />`,
    `<meta name="twitter:description" content="${description}" />`,
    ...preloadTags(path),
  ];
  return tags.join('\n    ');
}

/** The manifest keys of a chunk and every chunk it statically imports. */
function chunkClosure(key, seen = new Set()) {
  if (seen.has(key) || !manifest[key]) return seen;
  seen.add(key);
  for (const next of manifest[key].imports ?? []) chunkClosure(next, seen);
  return seen;
}

const entryChunks = chunkClosure('index.html');

/** The modulepreload links for the split page a route renders, if any. */
function preloadTags(path) {
  const source = pageSourceFor(path);
  if (!source) return [];
  if (!manifest[source]) {
    throw new Error(`The Vite manifest has no chunk for ${source}`);
  }
  return [...chunkClosure(source)]
    .filter((key) => !entryChunks.has(key))
    .map(
      (key) =>
        `<link rel="modulepreload" crossorigin href="/${escape(manifest[key].file)}" />`
    );
}

/** The file a route is written to. */
function outputPath(path) {
  if (path === '/') return indexPath;
  if (path === NOT_FOUND_PATH) return `${dist}/404.html`;
  return `${dist}${path}/index.html`;
}

const indexed = [];
for (const path of prerenderRoutes()) {
  const { html, meta } = render(path);
  const marker = escape(path);
  const shell = `<div id="root" data-prerendered="${marker}">${html}</div>`;
  const head = template.replace(headRegion, () => headTags(path, meta));
  const page = head.replace(placeholder, () => shell);
  const file = outputPath(path);
  await mkdir(dirname(file), { recursive: true });
  await writeFile(file, page);
  if (path !== NOT_FOUND_PATH && !meta.noindex) indexed.push(path);
  console.log(`Prerendered ${path}`);
}

const sitemap = [
  '<?xml version="1.0" encoding="UTF-8"?>',
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  ...indexed.map((path) => `  <url><loc>${escape(urlFor(path))}</loc></url>`),
  '</urlset>',
  '',
].join('\n');
await writeFile(`${dist}/sitemap.xml`, sitemap);
await writeFile(
  `${dist}/robots.txt`,
  `User-agent: *\nAllow: /\nSitemap: ${urlFor('/sitemap.xml')}\n`
);
await rm(ssrDir, { recursive: true, force: true });
await rm(manifestDir, { recursive: true, force: true });
console.log(
  `Wrote dist/sitemap.xml with ${indexed.length} URLs and dist/robots.txt`
);
