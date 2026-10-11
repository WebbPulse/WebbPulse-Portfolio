import { describe, expect, it } from 'vitest';
import {
  buildCommands,
  filterCommands,
  scoreCommand,
  type CommandSources,
} from './commands';

const sources: CommandSources = {
  nodes: [
    {
      id: 'standupless',
      label: 'Standupless',
      kind: 'Issue tracker',
      facts: ['MCP server'],
    },
  ],
  caseStudies: [{ slug: 'aws-organisation', title: 'AWS organisation' }],
  posts: [{ slug: 'hello', title: 'Hello world', excerpt: 'First post' }],
  navigation: [
    { label: 'Work', href: '#work' },
    { label: 'Writing', href: '/blog' },
    { label: 'Contact', href: '#contact' },
    { label: 'External', href: 'https://example.com' },
  ],
  resumeUrl: '/Profile.pdf',
};

describe('buildCommands', () => {
  const commands = buildCommands(sources);

  it('covers nodes, case studies, posts, pages and the theme', () => {
    expect(commands.find((c) => c.id === 'node-standupless')?.target).toEqual({
      kind: 'route',
      to: '/',
      focusNode: 'standupless',
    });
    expect(
      commands.find((c) => c.id === 'work-aws-organisation')?.target
    ).toEqual({ kind: 'route', to: '/work/aws-organisation' });
    expect(commands.find((c) => c.id === 'post-hello')?.target).toEqual({
      kind: 'route',
      to: '/blog/hello',
    });
    expect(commands.find((c) => c.label === 'Resume')?.target).toEqual({
      kind: 'file',
      href: '/Profile.pdf',
    });
    expect(commands.at(-1)?.target).toEqual({ kind: 'theme' });
  });

  it('turns navigation into pages and drops duplicates and externals', () => {
    const pages = commands.filter((c) => c.group === 'Pages');
    expect(pages.map((c) => c.label)).toEqual([
      'Home',
      'Work',
      'Writing',
      'Contact',
      'Resume',
      'Privacy',
    ]);
    expect(pages.find((c) => c.label === 'Work')?.target).toEqual({
      kind: 'anchor',
      id: 'work',
    });
  });
});

describe('filterCommands', () => {
  const commands = buildCommands(sources);

  it('returns everything for an empty query', () => {
    expect(filterCommands(commands, '  ')).toBe(commands);
  });

  it('ranks label prefixes above keyword matches', () => {
    const labels = filterCommands(commands, 'w').map((c) => c.label);
    expect(labels.slice(0, 2)).toEqual(['Work', 'Writing']);
  });

  it('matches keywords and requires every word', () => {
    expect(filterCommands(commands, 'mcp').map((c) => c.label)).toEqual([
      'Standupless',
    ]);
    expect(filterCommands(commands, 'mcp nothing')).toEqual([]);
  });
});

describe('scoreCommand', () => {
  it('scores label start, word start, substring and keyword', () => {
    const [command] = buildCommands({ ...sources, nodes: [] }).filter(
      (c) => c.label === 'AWS organisation'
    );
    if (!command) throw new Error('missing command');
    expect(scoreCommand(command, 'aws')).toBe(0);
    expect(scoreCommand(command, 'org')).toBe(1);
    expect(scoreCommand(command, 'ganis')).toBe(2);
    expect(scoreCommand(command, 'case study')).toBe(3);
    expect(scoreCommand(command, 'zzz')).toBeUndefined();
  });
});
