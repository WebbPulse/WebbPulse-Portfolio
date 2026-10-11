import type { NavigationItem } from '../../types';

/** The groups the command menu lists, in display order. */
export const COMMAND_GROUPS = [
  'Map',
  'Case studies',
  'Writing',
  'Pages',
  'Actions',
] as const;

/** One group of the command menu. */
export type CommandGroup = (typeof COMMAND_GROUPS)[number];

/** What running a command does. */
export type CommandTarget =
  | { kind: 'route'; to: string; focusNode?: string }
  | { kind: 'anchor'; id: string }
  | { kind: 'file'; href: string }
  | { kind: 'theme' };

/** One row of the command menu. */
export interface PaletteCommand {
  id: string;
  group: CommandGroup;
  label: string;
  hint: string;
  keywords: string[];
  target: CommandTarget;
}

/** The content the command menu is built from. */
export interface CommandSources {
  nodes: { id: string; label: string; kind: string; facts: string[] }[];
  caseStudies: { slug: string; title: string }[];
  posts: { slug: string; title: string; excerpt?: string | undefined }[];
  navigation: NavigationItem[];
  resumeUrl: string;
}

/** The target a navigation item points at. */
function navigationTarget(href: string): CommandTarget | undefined {
  const hash = href.indexOf('#');
  if (hash !== -1) return { kind: 'anchor', id: href.slice(hash + 1) };
  if (href.startsWith('/')) return { kind: 'route', to: href };
  return undefined;
}

/**
 * Every command: map nodes, case studies, posts, pages and the theme switch.
 *
 * Pages come from the site navigation plus home, the resume and privacy, with
 * a later page dropped when an earlier one already has its label.
 */
export function buildCommands(sources: CommandSources): PaletteCommand[] {
  const commands: PaletteCommand[] = [];
  for (const node of sources.nodes) {
    commands.push({
      id: `node-${node.id}`,
      group: 'Map',
      label: node.label,
      hint: node.kind,
      keywords: [node.kind, ...node.facts, 'map', 'system'],
      target: { kind: 'route', to: '/', focusNode: node.id },
    });
  }
  for (const study of sources.caseStudies) {
    commands.push({
      id: `work-${study.slug}`,
      group: 'Case studies',
      label: study.title,
      hint: 'Case study',
      keywords: [study.slug, 'work', 'case study'],
      target: { kind: 'route', to: `/work/${study.slug}` },
    });
  }
  for (const post of sources.posts) {
    commands.push({
      id: `post-${post.slug}`,
      group: 'Writing',
      label: post.title,
      hint: 'Post',
      keywords: [post.slug, 'blog', 'writing', post.excerpt ?? ''],
      target: { kind: 'route', to: `/blog/${post.slug}` },
    });
  }
  const pages: PaletteCommand[] = [
    {
      id: 'page-home',
      group: 'Pages',
      label: 'Home',
      hint: 'Page',
      keywords: ['start', 'index'],
      target: { kind: 'route', to: '/' },
    },
    ...sources.navigation.flatMap((item): PaletteCommand[] => {
      const target = navigationTarget(item.href);
      return target
        ? [
            {
              id: `page-${item.href}`,
              group: 'Pages',
              label: item.label,
              hint: target.kind === 'anchor' ? 'Section' : 'Page',
              keywords: [item.href],
              target,
            },
          ]
        : [];
    }),
    {
      id: 'page-resume',
      group: 'Pages',
      label: 'Resume',
      hint: 'PDF',
      keywords: ['cv', 'pdf', 'profile'],
      target: { kind: 'file', href: sources.resumeUrl },
    },
    {
      id: 'page-contact',
      group: 'Pages',
      label: 'Contact',
      hint: 'Section',
      keywords: ['email', 'github', 'linkedin', 'hire'],
      target: { kind: 'anchor', id: 'contact' },
    },
    {
      id: 'page-privacy',
      group: 'Pages',
      label: 'Privacy',
      hint: 'Page',
      keywords: ['policy'],
      target: { kind: 'route', to: '/privacy' },
    },
  ];
  const seen = new Set<string>();
  for (const page of pages) {
    const key = page.label.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    commands.push(page);
  }
  commands.push({
    id: 'action-theme',
    group: 'Actions',
    label: 'Switch theme',
    hint: 'Action',
    keywords: ['dark', 'light', 'mode', 'appearance'],
    target: { kind: 'theme' },
  });
  return commands;
}

/**
 * How well `command` matches the lowercase query `q`, lower is better, or
 * undefined when it does not match.
 *
 * Every word of the query has to appear in the label or a keyword. A label
 * that starts with the query beats one with a word starting with it, which
 * beats a label containing it, which beats a keyword match.
 */
export function scoreCommand(
  command: PaletteCommand,
  q: string
): number | undefined {
  const label = command.label.toLowerCase();
  const haystack = [label, ...command.keywords.map((k) => k.toLowerCase())];
  const words = q.split(/\s+/).filter(Boolean);
  if (!words.every((word) => haystack.some((text) => text.includes(word)))) {
    return undefined;
  }
  if (label.startsWith(q)) return 0;
  if (label.split(/[\s/@*-]+/).some((part) => part.startsWith(q))) return 1;
  if (label.includes(q)) return 2;
  return 3;
}

/**
 * The commands matching `query`, best first, keeping the original order
 * between equal matches. An empty query returns every command unchanged.
 */
export function filterCommands(
  commands: PaletteCommand[],
  query: string
): PaletteCommand[] {
  const q = query.trim().toLowerCase();
  if (!q) return commands;
  return commands
    .map((command, index) => ({
      command,
      index,
      score: scoreCommand(command, q),
    }))
    .filter(
      (row): row is { command: PaletteCommand; index: number; score: number } =>
        row.score !== undefined
    )
    .sort((a, b) => a.score - b.score || a.index - b.index)
    .map((row) => row.command);
}
