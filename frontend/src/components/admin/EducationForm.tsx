import React from 'react';
import { Button } from '../common';
import type { Education, EducationFormData } from './types';

interface EducationFormProps {
  form: EducationFormData;
  setForm: React.Dispatch<React.SetStateAction<EducationFormData>>;
  onSubmit: (e: React.FormEvent) => Promise<void>;
  onCancel: () => void;
  editingEducation: Education | null;
  loading: boolean;
}

const inputClass =
  'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white';
const labelClass =
  'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1';

export const EducationForm: React.FC<EducationFormProps> = ({
  form,
  setForm,
  onSubmit,
  onCancel,
  editingEducation,
  loading,
}) => {
  return (
    <div className="mb-6 bg-gray-50 dark:bg-gray-700 rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        {editingEducation ? 'Edit Education' : 'Add New Education'}
      </h3>
      <form onSubmit={e => void onSubmit(e)} className="space-y-4">
        <div>
          <label className={labelClass}>Degree *</label>
          <input
            type="text"
            value={form.degree}
            onChange={e =>
              setForm(prev => ({ ...prev, degree: e.target.value }))
            }
            className={inputClass}
            required
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className={labelClass}>School *</label>
            <input
              type="text"
              value={form.school}
              onChange={e =>
                setForm(prev => ({ ...prev, school: e.target.value }))
              }
              className={inputClass}
              required
            />
          </div>
          <div>
            <label className={labelClass}>Location *</label>
            <input
              type="text"
              value={form.location}
              onChange={e =>
                setForm(prev => ({ ...prev, location: e.target.value }))
              }
              className={inputClass}
              required
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className={labelClass}>Period (display) *</label>
            <input
              type="text"
              value={form.period}
              onChange={e =>
                setForm(prev => ({ ...prev, period: e.target.value }))
              }
              placeholder="e.g., Aug 2018 - May 2022"
              className={inputClass}
              required
            />
          </div>
          <div>
            <label className={labelClass}>Start Date *</label>
            <input
              type="date"
              value={form.start_date}
              onChange={e =>
                setForm(prev => ({ ...prev, start_date: e.target.value }))
              }
              className={inputClass}
              required
            />
          </div>
          <div>
            <label className={labelClass}>End Date</label>
            <input
              type="date"
              value={form.end_date}
              onChange={e =>
                setForm(prev => ({ ...prev, end_date: e.target.value }))
              }
              className={inputClass}
            />
          </div>
        </div>

        <div>
          <label className={labelClass}>Description</label>
          <textarea
            value={form.description}
            onChange={e =>
              setForm(prev => ({ ...prev, description: e.target.value }))
            }
            rows={3}
            className={inputClass}
          />
        </div>

        <div>
          <label className={labelClass}>Order</label>
          <input
            type="number"
            value={form.order}
            onChange={e =>
              setForm(prev => ({
                ...prev,
                order: Number(e.target.value) || 0,
              }))
            }
            className={inputClass}
          />
        </div>

        <div className="flex gap-2">
          <Button type="submit" variant="primary" disabled={loading}>
            {loading
              ? 'Saving...'
              : editingEducation
                ? 'Update Education'
                : 'Create Education'}
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
