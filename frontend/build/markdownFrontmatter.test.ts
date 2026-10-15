import { describe, expect, it } from 'vitest';
import { frontmatterOnly } from './markdownFrontmatter.ts';

describe('frontmatterOnly', () => {
  it('keeps the fields and flags a body', () => {
    expect(frontmatterOnly('---\ntitle: A\n---\n\n## Problem\nText\n')).toBe(
      '---\ntitle: A\nhas_write_up: true\n---\n'
    );
  });

  it('leaves an empty body unflagged', () => {
    expect(frontmatterOnly('---\nslug: b\n---\n\n')).toBe('---\nslug: b\n---\n');
  });

  it('flags a file without frontmatter that has text', () => {
    expect(frontmatterOnly('Just text')).toBe('---\nhas_write_up: true\n---\n');
  });
});
