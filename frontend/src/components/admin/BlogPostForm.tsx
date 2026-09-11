import React, { useState, useEffect } from 'react';
import { Button } from '../common';
import { apiService } from '../../services/api';
import type { BlogPost, BlogPostFormData, Category } from './types';
import { MarkdownPreview } from './MarkdownPreview';
import { MarkdownCheatsheet } from './MarkdownCheatsheet';

interface BlogPostFormProps {
  form: BlogPostFormData;
  setForm: React.Dispatch<React.SetStateAction<BlogPostFormData>>;
  onSubmit: (e: React.FormEvent) => Promise<void>;
  onCancel: () => void;
  editingPost: BlogPost | null;
  loading: boolean;
}

/** Create and edit form for a blog post. */
export const BlogPostForm: React.FC<BlogPostFormProps> = ({
  form,
  setForm,
  onSubmit,
  onCancel,
  editingPost,
  loading,
}) => {
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoriesLoading, setCategoriesLoading] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  useEffect(() => {
    void loadCategories();
  }, []);

  const loadCategories = async () => {
    setCategoriesLoading(true);
    const response = await apiService.getCategories();
    if (response.data) {
      setCategories(response.data);
    }
    setCategoriesLoading(false);
  };

  const generateSlug = () => {
    const slug = form.title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '');
    setForm(prev => ({ ...prev, slug }));
  };

  return (
    <div className="mb-6 bg-gray-50 dark:bg-gray-700 rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        {editingPost ? 'Edit Blog Post' : 'Add New Blog Post'}
      </h3>
      <form onSubmit={e => void onSubmit(e)} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Title *
          </label>
          <input
            type="text"
            value={form.title}
            onChange={e =>
              setForm(prev => ({
                ...prev,
                title: e.target.value,
              }))
            }
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Slug *
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={form.slug}
              onChange={e =>
                setForm(prev => ({
                  ...prev,
                  slug: e.target.value,
                }))
              }
              className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white"
              required
            />
            <Button
              type="button"
              variant="outline"
              onClick={generateSlug}
              disabled={!form.title}
            >
              Generate
            </Button>
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Category
          </label>
          <select
            value={form.category_id || ''}
            onChange={e =>
              setForm(prev => ({
                ...prev,
                category_id: e.target.value
                  ? Number(e.target.value)
                  : undefined,
              }))
            }
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white"
            disabled={categoriesLoading}
          >
            <option value="">Select a category</option>
            {categories.map(category => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Excerpt
          </label>
          <textarea
            value={form.excerpt}
            onChange={e =>
              setForm(prev => ({
                ...prev,
                excerpt: e.target.value,
              }))
            }
            rows={3}
            placeholder="Brief summary of the post..."
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Read Time
          </label>
          <input
            type="text"
            value={form.read_time}
            onChange={e =>
              setForm(prev => ({
                ...prev,
                read_time: e.target.value,
              }))
            }
            placeholder="e.g., 5 min read"
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white"
          />
        </div>
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Content *
            </label>
            <div className="flex items-center gap-2">
              <MarkdownCheatsheet />
              <button
                type="button"
                onClick={() => setShowPreview(!showPreview)}
                className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-md transition-all duration-200"
                title={showPreview ? 'Hide live preview' : 'Show live preview'}
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
                    d={
                      showPreview
                        ? 'M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z'
                        : 'M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z'
                    }
                  />
                </svg>
                <span>{showPreview ? 'Hide Preview' : 'Show Preview'}</span>
                <svg
                  className={`w-3 h-3 transition-transform duration-200 ${
                    showPreview ? 'rotate-180' : ''
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
            </div>
          </div>

          <div className="transition-all duration-300 ease-in-out">
            {showPreview ? (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 animate-in slide-in-from-bottom-2 duration-300">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Markdown Editor
                  </label>
                  <textarea
                    value={form.content}
                    onChange={e =>
                      setForm(prev => ({
                        ...prev,
                        content: e.target.value,
                      }))
                    }
                    rows={15}
                    placeholder="Write your blog post content here... (Markdown supported)"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white font-mono text-sm"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Live Preview
                  </label>
                  <div className="border border-gray-300 dark:border-gray-600 rounded-md p-4 bg-white dark:bg-gray-600 h-full overflow-y-auto">
                    <MarkdownPreview content={form.content} />
                  </div>
                </div>
              </div>
            ) : (
              <div className="animate-in slide-in-from-bottom-2 duration-300">
                <textarea
                  value={form.content}
                  onChange={e =>
                    setForm(prev => ({
                      ...prev,
                      content: e.target.value,
                    }))
                  }
                  rows={15}
                  placeholder="Write your blog post content here... (Markdown supported)"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white font-mono text-sm"
                  required
                />
              </div>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <Button type="submit" variant="primary" disabled={loading}>
            {loading
              ? 'Saving...'
              : editingPost
                ? 'Update Post'
                : 'Create Post'}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={loading}
          >
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
};
