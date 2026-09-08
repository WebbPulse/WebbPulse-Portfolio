import React, { useState } from 'react';

export const MarkdownCheatsheet: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const cheatsheetItems = [
    {
      title: 'Headers',
      icon: 'H',
      examples: [
        { syntax: '# H1', description: 'Main heading' },
        { syntax: '## H2', description: 'Section heading' },
        { syntax: '### H3', description: 'Subsection heading' },
      ],
    },
    {
      title: 'Text Formatting',
      icon: 'T',
      examples: [
        { syntax: '**bold**', description: 'Bold text' },
        { syntax: '*italic*', description: 'Italic text' },
        { syntax: '~~strikethrough~~', description: 'Strikethrough text' },
      ],
    },
    {
      title: 'Links & Images',
      icon: '🔗',
      examples: [
        { syntax: '[text](url)', description: 'Link' },
        { syntax: '![alt](url)', description: 'Image' },
      ],
    },
    {
      title: 'Lists',
      icon: '📝',
      examples: [
        { syntax: '- item', description: 'Unordered list' },
        { syntax: '1. item', description: 'Ordered list' },
      ],
    },
    {
      title: 'Code',
      icon: '💻',
      examples: [
        { syntax: '`code`', description: 'Inline code' },
        { syntax: '```\ncode block\n```', description: 'Code block' },
      ],
    },
    {
      title: 'Quotes',
      icon: '💬',
      examples: [{ syntax: '> quote', description: 'Blockquote' }],
    },
    {
      title: 'Tables',
      icon: '📊',
      examples: [
        {
          syntax:
            '| Header | Header |\n|--------|--------|\n| Cell   | Cell   |',
          description: 'Table',
        },
      ],
    },
  ];

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      // You could add a toast notification here
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-md transition-colors duration-200"
        title="Markdown syntax reference"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <span>Markdown</span>
        <svg
          className={`w-3 h-3 transition-transform duration-200 ${
            isOpen ? 'rotate-180' : ''
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-1 w-80 max-h-96 overflow-y-auto bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-lg z-50">
          <div className="p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
                Markdown Syntax Reference
              </h4>
              <button
                onClick={() => setIsOpen(false)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>

            <div className="space-y-4">
              {cheatsheetItems.map((section, index) => (
                <div
                  key={index}
                  className="border-b border-gray-100 dark:border-gray-700 last:border-b-0 pb-3 last:pb-0"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      {section.icon}
                    </span>
                    <h5 className="text-xs font-medium text-gray-700 dark:text-gray-300 uppercase tracking-wide">
                      {section.title}
                    </h5>
                  </div>
                  <div className="space-y-1.5">
                    {section.examples.map((example, exampleIndex) => (
                      <div key={exampleIndex} className="group">
                        <div className="flex items-center justify-between p-2 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors duration-150">
                          <div className="flex-1 min-w-0">
                            <code className="block text-xs bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-gray-800 dark:text-gray-200 font-mono break-all">
                              {example.syntax}
                            </code>
                            <span className="block text-xs text-gray-600 dark:text-gray-400 mt-1">
                              {example.description}
                            </span>
                          </div>
                          <button
                            onClick={() => void copyToClipboard(example.syntax)}
                            className="ml-2 p-1 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 opacity-0 group-hover:opacity-100 transition-opacity duration-150"
                            title="Copy to clipboard"
                          >
                            <svg
                              className="w-3 h-3"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                              />
                            </svg>
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
