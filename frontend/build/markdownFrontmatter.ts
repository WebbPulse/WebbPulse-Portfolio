import type { Plugin } from 'vite';

const QUERY = /[?&]frontmatter(?:&|$)/;
const FENCE = '---';
const EXPORT = /^export default\s*("(?:[^"\\]|\\.)*")\s*;?\s*$/;

/**
 * Cuts a markdown file down to its frontmatter.
 *
 * The fields are kept as written and `has_write_up: true` is added when the
 * file has a body, so a listing knows a write-up exists without carrying it.
 */
export function frontmatterOnly(raw: string): string {
  const lines = raw.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').split('\n');
  const end =
    lines[0]?.trim() === FENCE
      ? lines.findIndex((line, i) => i > 0 && line.trim() === FENCE)
      : -1;
  const fields = end === -1 ? [] : lines.slice(1, end);
  const body = (end === -1 ? lines : lines.slice(end + 1)).join('\n').trim();
  if (body) fields.push('has_write_up: true');
  return [FENCE, ...fields, FENCE, ''].join('\n');
}

/**
 * Serves `file.md?raw&frontmatter` as the file's frontmatter alone, so the
 * home page bundle lists case studies and posts without their bodies.
 */
export function markdownFrontmatter(): Plugin {
  return {
    name: 'webbpulse:markdown-frontmatter',
    transform(code, id) {
      if (!QUERY.test(id)) return null;
      const match = EXPORT.exec(code.trim());
      const literal = match?.[1];
      if (literal === undefined) {
        throw new Error(`Expected a raw string export for ${id}`);
      }
      const raw = JSON.parse(literal) as string;
      return {
        code: `export default ${JSON.stringify(frontmatterOnly(raw))};`,
        map: null,
      };
    },
  };
}
