import { describe, it, expect } from 'vitest';
import {
  processMarkdown,
  extractHeadings,
  calculateReadingTime,
} from './markdown';

describe('Markdown Utils', () => {
  describe('processMarkdown', () => {
    it('should convert markdown to HTML with styling', () => {
      const markdown = '# Test Heading\n\nThis is a **bold** paragraph.';
      const result = processMarkdown(markdown);

      expect(result).toContain('<h1');
      expect(result).toContain('<p');
      expect(result).toContain('<strong');
      expect(result).toContain('class=');
    });

    it('should handle empty markdown', () => {
      const result = processMarkdown('');
      expect(result).toBe('');
    });
  });

  describe('extractHeadings', () => {
    it('should extract headings from markdown', () => {
      const markdown = `
# Main Heading
## Sub Heading
### Another Heading
Regular text
## Another Sub Heading
      `;

      const headings = extractHeadings(markdown);

      expect(headings).toHaveLength(3);
      expect(headings[0]).toEqual({
        level: 2,
        text: 'Sub Heading',
        id: 'sub-heading',
      });
      expect(headings[1]).toEqual({
        level: 3,
        text: 'Another Heading',
        id: 'another-heading',
      });
      expect(headings[2]).toEqual({
        level: 2,
        text: 'Another Sub Heading',
        id: 'another-sub-heading',
      });
    });

    it('should handle markdown without headings', () => {
      const markdown = 'This is just regular text with no headings.';
      const headings = extractHeadings(markdown);
      expect(headings).toHaveLength(0);
    });
  });

  describe('calculateReadingTime', () => {
    it('should calculate reading time correctly', () => {
      const markdown = 'This is a test paragraph with some words. '.repeat(17);
      const readingTime = calculateReadingTime(markdown);
      expect(readingTime).toBe(1);
    });

    it('should return minimum 1 minute for short content', () => {
      const markdown = 'Short content';
      const readingTime = calculateReadingTime(markdown);
      expect(readingTime).toBe(1);
    });

    it('should handle empty content', () => {
      const readingTime = calculateReadingTime('');
      expect(readingTime).toBe(1);
    });
  });
});
