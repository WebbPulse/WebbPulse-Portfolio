import { describe, expect, it } from 'vitest';
import { parseFrontmatter } from './frontmatter';

describe('parseFrontmatter', () => {
  it('splits flat fields from the body', () => {
    const parsed = parseFrontmatter(
      '---\ntitle: Hello\nslug: hello-world\n---\n\n# Heading\n\nText'
    );

    expect(parsed.data).toEqual({ title: 'Hello', slug: 'hello-world' });
    expect(parsed.body).toBe('# Heading\n\nText');
  });

  it('removes matching quotes and keeps colons inside values', () => {
    const parsed = parseFrontmatter(
      '---\ntitle: "A: B"\nexcerpt: \'quoted\'\nodd: "half\n---\nbody'
    );

    expect(parsed.data).toEqual({
      title: 'A: B',
      excerpt: 'quoted',
      odd: '"half',
    });
  });

  it('normalises CRLF line endings and a byte order mark', () => {
    const parsed = parseFrontmatter('﻿---\r\ntitle: Win\r\n---\r\nLine');

    expect(parsed.data).toEqual({ title: 'Win' });
    expect(parsed.body).toBe('Line');
  });

  it('treats a file without a fence as all body', () => {
    expect(parseFrontmatter('Just text')).toEqual({
      data: {},
      body: 'Just text',
    });
  });

  it('treats an unclosed fence as all body', () => {
    expect(parseFrontmatter('---\ntitle: x\nbody')).toEqual({
      data: {},
      body: '---\ntitle: x\nbody',
    });
  });

  it('ignores lines that are not key value pairs', () => {
    const parsed = parseFrontmatter('---\n# note\ntitle: Kept\n\n---\nbody');

    expect(parsed.data).toEqual({ title: 'Kept' });
  });
});
