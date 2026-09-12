import React from 'react';
import { Button } from '../common';
import type { Skill, SkillFormData, SkillTier } from './types';

interface SkillFormProps {
  form: SkillFormData;
  setForm: React.Dispatch<React.SetStateAction<SkillFormData>>;
  onSubmit: (e: React.FormEvent) => Promise<void>;
  onCancel: () => void;
  editingSkill: Skill | null;
  loading: boolean;
}

const inputClass =
  'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white';
const labelClass =
  'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1';

/** Create and edit form for a skill. */
export const SkillForm: React.FC<SkillFormProps> = ({
  form,
  setForm,
  onSubmit,
  onCancel,
  editingSkill,
  loading,
}) => {
  return (
    <div className="mb-6 bg-gray-50 dark:bg-gray-700 rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        {editingSkill ? 'Edit Skill' : 'Add New Skill'}
      </h3>
      <form onSubmit={(e) => void onSubmit(e)} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>Name *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, name: e.target.value }))
              }
              className={inputClass}
              required
            />
          </div>
          <div>
            <label className={labelClass}>Category *</label>
            <select
              value={form.category}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  category: e.target.value as SkillFormData['category'],
                }))
              }
              className={inputClass}
              required
            >
              <option value="frontend">Frontend</option>
              <option value="backend">Backend</option>
              <option value="devops">DevOps</option>
              <option value="cloud">Cloud Platforms</option>
              <option value="networking">Networking &amp; IT</option>
              <option value="other">Other</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className={labelClass}>Icon</label>
            <input
              type="text"
              value={form.icon}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, icon: e.target.value }))
              }
              placeholder="si:react or 🤖"
              className={inputClass}
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Emoji, or <code>si:&lt;name&gt;</code> for a brand logo (e.g.{' '}
              <code>si:react</code>, <code>si:python</code>).
            </p>
          </div>
          <div>
            <label className={labelClass}>Order</label>
            <input
              type="number"
              value={form.order}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  order: Number(e.target.value) || 0,
                }))
              }
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Tier</label>
            <select
              value={form.tier}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  tier: e.target.value as SkillTier,
                }))
              }
              className={inputClass}
              required
            >
              <option value="core">Core — use daily, deep</option>
              <option value="working">Working — ship in it comfortably</option>
              <option value="familiar">Familiar — can read/contribute</option>
            </select>
          </div>
        </div>

        <div className="flex gap-2">
          <Button type="submit" variant="primary" disabled={loading}>
            {loading
              ? 'Saving...'
              : editingSkill
                ? 'Update Skill'
                : 'Create Skill'}
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
