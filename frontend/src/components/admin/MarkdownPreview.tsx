import React from 'react';
import { processMarkdown } from '../../utils/markdown';

interface MarkdownPreviewProps {
  content: string;
  className?: string;
}

/** Renders markdown as the sanitised HTML the site will show. */
export const MarkdownPreview: React.FC<MarkdownPreviewProps> = ({
  content,
  className = '',
}) => {
  if (!content.trim()) {
    return (
      <div className={`text-gray-500 dark:text-gray-400 italic ${className}`}>
        Preview will appear here as you type...
      </div>
    );
  }

  const processedContent = processMarkdown(content);

  return (
    <div className={`prose prose-sm dark:prose-invert max-w-none ${className}`}>
      <div
        className="text-gray-700 dark:text-gray-300 leading-relaxed"
        dangerouslySetInnerHTML={{ __html: processedContent }}
      />
    </div>
  );
};
