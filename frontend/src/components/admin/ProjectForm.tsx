import React from 'react';
import { Button } from '../common';
import type { Project, ProjectFormData } from './types';

interface ProjectFormProps {
  form: ProjectFormData;
  setForm: React.Dispatch<React.SetStateAction<ProjectFormData>>;
  onSubmit: (e: React.FormEvent) => Promise<void>;
  onCancel: () => void;
  editingProject: Project | null;
  loading: boolean;
}

/** Create and edit form for a project. */
export const ProjectForm: React.FC<ProjectFormProps> = ({
  form,
  setForm,
  onSubmit,
  onCancel,
  editingProject,
  loading,
}) => {
  const addTechnology = () => {
    const tech = prompt('Enter technology:');
    if (tech) {
      setForm(prev => ({
        ...prev,
        technologies: [...prev.technologies, tech],
      }));
    }
  };

  const removeTechnology = (index: number) => {
    setForm(prev => ({
      ...prev,
      technologies: prev.technologies.filter((_, i) => i !== index),
    }));
  };

  return (
    <div className="mb-6 bg-gray-50 dark:bg-gray-700 rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        {editingProject ? 'Edit Project' : 'Add New Project'}
      </h3>
      <form onSubmit={e => void onSubmit(e)} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
              Image URL or path
            </label>
            <input
              type="text"
              value={form.image}
              onChange={e =>
                setForm(prev => ({
                  ...prev,
                  image: e.target.value,
                }))
              }
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white"
            />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Description *
          </label>
          <textarea
            value={form.description}
            onChange={e =>
              setForm(prev => ({
                ...prev,
                description: e.target.value,
              }))
            }
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white"
            required
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              GitHub URL
            </label>
            <input
              type="url"
              value={form.github_url}
              onChange={e =>
                setForm(prev => ({
                  ...prev,
                  github_url: e.target.value,
                }))
              }
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Live URL
            </label>
            <input
              type="url"
              value={form.live_url}
              onChange={e =>
                setForm(prev => ({
                  ...prev,
                  live_url: e.target.value,
                }))
              }
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white"
            />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Technologies
          </label>
          <div className="flex flex-wrap gap-2 mb-2">
            {form.technologies.map((tech, index) => (
              <span
                key={index}
                className="px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full text-sm flex items-center"
              >
                {tech}
                <button
                  type="button"
                  onClick={() => removeTechnology(index)}
                  className="ml-1 text-blue-600 hover:text-blue-800"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={addTechnology}
          >
            Add Technology
          </Button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
          <div className="flex items-center">
            <input
              type="checkbox"
              id="featured"
              checked={form.featured}
              onChange={e =>
                setForm(prev => ({
                  ...prev,
                  featured: e.target.checked,
                }))
              }
              className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
            />
            <label
              htmlFor="featured"
              className="ml-2 block text-sm text-gray-900 dark:text-gray-300"
            >
              Featured Project
            </label>
          </div>
          <div>
            <label
              htmlFor="display_order"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Display order
            </label>
            <input
              type="number"
              id="display_order"
              value={form.display_order}
              onChange={e =>
                setForm(prev => ({
                  ...prev,
                  display_order: Number(e.target.value),
                }))
              }
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Lower numbers appear first (used when site sort mode is "Manual").
              Featured projects always appear above non-featured.
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button type="submit" variant="primary" disabled={loading}>
            {loading
              ? 'Saving...'
              : editingProject
                ? 'Update Project'
                : 'Create Project'}
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
