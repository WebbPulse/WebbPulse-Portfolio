import React from 'react';
import { Button } from '../common';
import type { SiteContentFormData } from './types';

interface SiteContentFormProps {
  form: SiteContentFormData;
  setForm: React.Dispatch<React.SetStateAction<SiteContentFormData>>;
  onSubmit: (e: React.FormEvent) => Promise<void>;
  loading: boolean;
}

const inputClass =
  'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white';
const labelClass =
  'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1';

/** Edit form for the singleton site content record. */
export const SiteContentForm: React.FC<SiteContentFormProps> = ({
  form,
  setForm,
  onSubmit,
  loading,
}) => {
  const updateParagraph = (index: number, value: string) =>
    setForm((prev) => ({
      ...prev,
      about_paragraphs: prev.about_paragraphs.map((p, i) =>
        i === index ? value : p
      ),
    }));

  const addParagraph = () =>
    setForm((prev) => ({
      ...prev,
      about_paragraphs: [...prev.about_paragraphs, ''],
    }));

  const removeParagraph = (index: number) =>
    setForm((prev) => ({
      ...prev,
      about_paragraphs: prev.about_paragraphs.filter((_, i) => i !== index),
    }));

  const updateValue = (
    index: number,
    field: 'title' | 'description' | 'icon',
    value: string
  ) =>
    setForm((prev) => ({
      ...prev,
      about_values: prev.about_values.map((v, i) =>
        i === index ? { ...v, [field]: value } : v
      ),
    }));

  const addValue = () =>
    setForm((prev) => ({
      ...prev,
      about_values: [
        ...prev.about_values,
        { title: '', description: '', icon: '' },
      ],
    }));

  const removeValue = (index: number) =>
    setForm((prev) => ({
      ...prev,
      about_values: prev.about_values.filter((_, i) => i !== index),
    }));

  return (
    <form onSubmit={(e) => void onSubmit(e)} className="space-y-8">
      <section className="bg-gray-50 dark:bg-gray-700 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Hero
        </h3>
        <div className="space-y-4">
          <div>
            <label className={labelClass}>Title</label>
            <input
              type="text"
              value={form.hero_title}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, hero_title: e.target.value }))
              }
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Subtitle</label>
            <input
              type="text"
              value={form.hero_subtitle}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, hero_subtitle: e.target.value }))
              }
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Description</label>
            <textarea
              value={form.hero_description}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  hero_description: e.target.value,
                }))
              }
              rows={3}
              className={inputClass}
            />
          </div>
        </div>
      </section>

      <section className="bg-gray-50 dark:bg-gray-700 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          About — Paragraphs
        </h3>
        <div className="space-y-3">
          {form.about_paragraphs.map((p, i) => (
            <div key={i} className="flex gap-2">
              <textarea
                value={p}
                onChange={(e) => updateParagraph(i, e.target.value)}
                rows={3}
                className={inputClass}
              />
              <button
                type="button"
                onClick={() => removeParagraph(i)}
                className="px-3 text-red-600 dark:text-red-400 hover:text-red-800"
                aria-label={`Remove paragraph ${i + 1}`}
              >
                ×
              </button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={addParagraph}
          >
            Add Paragraph
          </Button>
        </div>

        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-4">
          About — Values
        </h3>
        <div className="space-y-4">
          {form.about_values.map((v, i) => (
            <div
              key={i}
              className="grid grid-cols-1 md:grid-cols-12 gap-3 items-start"
            >
              <input
                type="text"
                value={v.icon}
                onChange={(e) => updateValue(i, 'icon', e.target.value)}
                placeholder="✨"
                className={`${inputClass} md:col-span-1`}
              />
              <input
                type="text"
                value={v.title}
                onChange={(e) => updateValue(i, 'title', e.target.value)}
                placeholder="Title"
                className={`${inputClass} md:col-span-3`}
              />
              <input
                type="text"
                value={v.description}
                onChange={(e) => updateValue(i, 'description', e.target.value)}
                placeholder="Description"
                className={`${inputClass} md:col-span-7`}
              />
              <button
                type="button"
                onClick={() => removeValue(i)}
                className="md:col-span-1 px-3 py-2 text-red-600 dark:text-red-400 hover:text-red-800"
                aria-label={`Remove value ${i + 1}`}
              >
                Remove
              </button>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={addValue}>
            Add Value
          </Button>
        </div>
      </section>

      <section className="bg-gray-50 dark:bg-gray-700 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Profile & Links
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Profile Image URL</label>
            <input
              type="text"
              value={form.profile_image_url}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  profile_image_url: e.target.value,
                }))
              }
              placeholder="/headshot.jpg"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Resume URL</label>
            <input
              type="text"
              value={form.resume_url}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, resume_url: e.target.value }))
              }
              placeholder="/Profile.pdf"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Email</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, email: e.target.value }))
              }
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>GitHub URL</label>
            <input
              type="url"
              value={form.github_url}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, github_url: e.target.value }))
              }
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>LinkedIn URL</label>
            <input
              type="url"
              value={form.linkedin_url}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, linkedin_url: e.target.value }))
              }
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Footer Tagline</label>
            <input
              type="text"
              value={form.footer_tagline}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, footer_tagline: e.target.value }))
              }
              className={inputClass}
            />
          </div>
        </div>
      </section>

      <section className="bg-gray-50 dark:bg-gray-700 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Projects
        </h3>
        <div>
          <label className={labelClass}>Project sort order</label>
          <select
            value={form.project_sort_mode}
            onChange={(e) =>
              setForm((prev) => ({
                ...prev,
                project_sort_mode: e.target.value,
              }))
            }
            className={inputClass}
          >
            <option value="manual">Manual (use each project's order)</option>
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="title_asc">Title (A–Z)</option>
          </select>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Controls how the projects section is ordered on the site. Featured
            projects always appear above non-featured ones; this setting orders
            projects within each group.
          </p>
        </div>
      </section>

      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={loading}>
          {loading ? 'Saving…' : 'Save Site Content'}
        </Button>
      </div>
    </form>
  );
};
