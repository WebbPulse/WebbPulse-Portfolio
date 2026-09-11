import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({
  gfm: true,
  breaks: true,
});

/**
 * Convert markdown content to HTML with proper styling
 * @param markdown - Raw markdown content
 * @returns Sanitized HTML string
 */
export const processMarkdown = (markdown: string): string => {
  const html = marked(markdown) as string;

  let sanitizedHtml = html;
  if (typeof window !== 'undefined' && DOMPurify.sanitize) {
    sanitizedHtml = DOMPurify.sanitize(html, {
      ALLOWED_TAGS: [
        'h1',
        'h2',
        'h3',
        'h4',
        'h5',
        'h6',
        'p',
        'br',
        'hr',
        'ul',
        'ol',
        'li',
        'blockquote',
        'pre',
        'code',
        'table',
        'thead',
        'tbody',
        'tr',
        'th',
        'td',
        'a',
        'img',
        'strong',
        'em',
        'del',
        'ins',
        'div',
        'span',
      ],
      ALLOWED_ATTR: [
        'href',
        'src',
        'alt',
        'title',
        'id',
        'class',
        'target',
        'rel',
      ],
      ALLOW_DATA_ATTR: false,
    });
  }

  const styledHtml = addCustomStyling(sanitizedHtml);

  return styledHtml;
};

/**
 * Add custom Tailwind CSS classes to HTML elements
 * @param html - Sanitized HTML string
 * @returns HTML with custom styling classes
 */
const addCustomStyling = (html: string): string => {
  return html
    .replace(
      /<h1([^>]*)>/g,
      '<h1$1 class="text-4xl font-bold text-gray-900 dark:text-white mb-6">'
    )
    .replace(
      /<h2([^>]*)>/g,
      '<h2$1 class="text-3xl font-bold text-gray-900 dark:text-white mb-5 mt-8">'
    )
    .replace(
      /<h3([^>]*)>/g,
      '<h3$1 class="text-2xl font-semibold text-gray-900 dark:text-white mb-4 mt-6">'
    )
    .replace(
      /<h4([^>]*)>/g,
      '<h4$1 class="text-xl font-semibold text-gray-900 dark:text-white mb-3 mt-5">'
    )
    .replace(
      /<h5([^>]*)>/g,
      '<h5$1 class="text-lg font-medium text-gray-900 dark:text-white mb-2 mt-4">'
    )
    .replace(
      /<h6([^>]*)>/g,
      '<h6$1 class="text-base font-medium text-gray-900 dark:text-white mb-2 mt-3">'
    )
    .replace(
      /<p([^>]*)>/g,
      '<p$1 class="text-gray-700 dark:text-gray-300 leading-relaxed mb-4">'
    )
    .replace(
      /<a([^>]*)>/g,
      '<a$1 class="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 underline transition-colors" target="_blank" rel="noopener noreferrer">'
    )
    .replace(
      /<ul([^>]*)>/g,
      '<ul$1 class="list-disc list-inside text-gray-700 dark:text-gray-300 mb-4 space-y-1">'
    )
    .replace(
      /<ol([^>]*)>/g,
      '<ol$1 class="list-decimal list-inside text-gray-700 dark:text-gray-300 mb-4 space-y-1">'
    )
    .replace(/<li([^>]*)>/g, '<li$1 class="mb-1">')
    .replace(
      /<blockquote([^>]*)>/g,
      '<blockquote$1 class="border-l-4 border-blue-500 pl-4 italic text-gray-600 dark:text-gray-400 mb-4">'
    )
    .replace(
      /<pre([^>]*)>/g,
      '<pre$1 class="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 overflow-x-auto mb-4">'
    )
    .replace(
      /<code([^>]*)>/g,
      '<code$1 class="text-sm font-mono text-gray-800 dark:text-gray-200">'
    )
    .replace(
      /<code([^>]*)>/g,
      '<code$1 class="bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 px-2 py-1 rounded text-sm font-mono">'
    )
    .replace(
      /<table([^>]*)>/g,
      '<div class="overflow-x-auto mb-4"><table$1 class="min-w-full border border-gray-300 dark:border-gray-600">'
    )
    .replace(/<\/table>/g, '</table></div>')
    .replace(
      /<tr([^>]*)>/g,
      '<tr$1 class="border-b border-gray-300 dark:border-gray-600">'
    )
    .replace(
      /<th([^>]*)>/g,
      '<th$1 class="px-4 py-2 bg-gray-50 dark:bg-gray-700 font-semibold text-left border-r border-gray-300 dark:border-gray-600">'
    )
    .replace(
      /<td([^>]*)>/g,
      '<td$1 class="px-4 py-2 border-r border-gray-300 dark:border-gray-600">'
    )
    .replace(
      /<img([^>]*)>/g,
      '<img$1 class="max-w-full h-auto rounded-lg shadow-md my-4">'
    )
    .replace(
      /<hr([^>]*)>/g,
      '<hr$1 class="border-gray-300 dark:border-gray-600 my-8">'
    )
    .replace(
      /<strong([^>]*)>/g,
      '<strong$1 class="font-bold text-gray-900 dark:text-white">'
    )
    .replace(
      /<em([^>]*)>/g,
      '<em$1 class="italic text-gray-800 dark:text-gray-200">'
    );
};

/**
 * Extract headings from markdown content for table of contents
 * @param markdown - Raw markdown content
 * @returns Array of heading objects with level, text, and id
 */
export const extractHeadings = (
  markdown: string
): Array<{ level: number; text: string; id: string }> => {
  const headings: Array<{ level: number; text: string; id: string }> = [];
  const lines = markdown.split('\n');

  for (const line of lines) {
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    const [, hashes, rawText] = headingMatch ?? [];
    if (hashes !== undefined && rawText !== undefined) {
      const level = hashes.length;
      const text = rawText.trim();
      const id = text.toLowerCase().replace(/[^\w]+/g, '-');

      if (level >= 2 && level <= 3) {
        headings.push({ level, text, id });
      }
    }
  }

  return headings;
};

/**
 * Calculate estimated reading time for markdown content
 * @param markdown - Raw markdown content
 * @returns Estimated reading time in minutes
 */
export const calculateReadingTime = (markdown: string): number => {
  const wordsPerMinute = 200;
  const wordCount = markdown.split(/\s+/).length;
  const readingTime = Math.ceil(wordCount / wordsPerMinute);
  return Math.max(1, readingTime);
};
