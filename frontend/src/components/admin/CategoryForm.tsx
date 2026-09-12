import React from 'react';
import { Button } from '../common';
import type { CategoryFormData, Category } from './types';

interface CategoryFormProps {
  form: CategoryFormData;
  setForm: React.Dispatch<React.SetStateAction<CategoryFormData>>;
  onSubmit: (e: React.FormEvent) => void;
  onCancel: () => void;
  editingCategory: Category | null;
  loading: boolean;
}

/** Create and edit form for a blog category. */
export const CategoryForm: React.FC<CategoryFormProps> = ({
  form,
  setForm,
  onSubmit,
  onCancel,
  editingCategory,
  loading,
}) => {
  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  return (
    <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-6 mb-6">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        {editingCategory ? 'Edit Category' : 'Add New Category'}
      </h3>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label
            htmlFor="name"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            Category Name *
          </label>
          <input
            type="text"
            id="name"
            name="name"
            value={form.name}
            onChange={handleInputChange}
            required
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-800 dark:text-white"
            placeholder="e.g., Web Development"
          />
        </div>

        <div>
          <label
            htmlFor="slug"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            Slug *
          </label>
          <input
            type="text"
            id="slug"
            name="slug"
            value={form.slug}
            onChange={handleInputChange}
            required
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-800 dark:text-white"
            placeholder="e.g., web-development"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
            URL-friendly version of the category name
          </p>
        </div>

        <div>
          <label
            htmlFor="description"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            Description
          </label>
          <textarea
            id="description"
            name="description"
            value={form.description}
            onChange={handleInputChange}
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-800 dark:text-white"
            placeholder="Brief description of the category"
          />
        </div>

        <div className="flex gap-3 pt-4">
          <Button
            type="submit"
            variant="primary"
            disabled={loading}
            className="flex-1"
          >
            {loading
              ? 'Saving...'
              : editingCategory
                ? 'Update Category'
                : 'Create Category'}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={loading}
            className="flex-1"
          >
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
};
