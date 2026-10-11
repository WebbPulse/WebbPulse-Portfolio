/** A markdown file split into its frontmatter fields and its body. */
export interface ParsedMarkdown {
  data: Record<string, string>;
  body: string;
}

const FENCE = '---';

/** Strips one pair of matching single or double quotes around a value. */
function unquote(value: string): string {
  const first = value[0];
  if (
    value.length >= 2 &&
    (first === '"' || first === "'") &&
    value[value.length - 1] === first
  ) {
    return value.slice(1, -1);
  }
  return value;
}

/**
 * Splits a markdown file into flat `key: value` frontmatter and its body.
 *
 * Only single line scalar values are read, which is all the content files use.
 * A file without a leading `---` fence is all body.
 */
export function parseFrontmatter(raw: string): ParsedMarkdown {
  const text = raw.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n');
  const lines = text.split('\n');
  if (lines[0]?.trim() !== FENCE) {
    return { data: {}, body: text };
  }
  const end = lines.findIndex((line, i) => i > 0 && line.trim() === FENCE);
  if (end === -1) {
    return { data: {}, body: text };
  }
  const data: Record<string, string> = {};
  for (const line of lines.slice(1, end)) {
    const match = /^([A-Za-z_][\w-]*)\s*:\s*(.*)$/.exec(line);
    const key = match?.[1];
    const value = match?.[2];
    if (key !== undefined && value !== undefined) {
      data[key] = unquote(value.trim());
    }
  }
  const body = lines
    .slice(end + 1)
    .join('\n')
    .replace(/^\n+/, '');
  return { data, body };
}
