import React from 'react';
import { Button } from '../common';
import type { Certification, CertificationFormData } from './types';

interface CertificationFormProps {
  form: CertificationFormData;
  setForm: React.Dispatch<React.SetStateAction<CertificationFormData>>;
  onSubmit: (e: React.FormEvent) => Promise<void>;
  onCancel: () => void;
  editingCertification: Certification | null;
  loading: boolean;
}

const inputClass =
  'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 dark:bg-gray-600 dark:text-white';
const labelClass =
  'block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1';

/** Create and edit form for a certification. */
export const CertificationForm: React.FC<CertificationFormProps> = ({
  form,
  setForm,
  onSubmit,
  onCancel,
  editingCertification,
  loading,
}) => {
  return (
    <div className="mb-6 bg-gray-50 dark:bg-gray-700 rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        {editingCertification ? 'Edit Certification' : 'Add New Certification'}
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
            <label className={labelClass}>Issuer *</label>
            <input
              type="text"
              value={form.issuer}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, issuer: e.target.value }))
              }
              className={inputClass}
              required
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className={labelClass}>Issued Date *</label>
            <input
              type="date"
              value={form.issued_date}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, issued_date: e.target.value }))
              }
              className={inputClass}
              required
            />
          </div>
          <div className="md:col-span-2">
            <label className={labelClass}>Credential URL</label>
            <input
              type="url"
              value={form.credential_url}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, credential_url: e.target.value }))
              }
              placeholder="https://..."
              className={inputClass}
            />
          </div>
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

        <div className="flex gap-2">
          <Button type="submit" variant="primary" disabled={loading}>
            {loading
              ? 'Saving...'
              : editingCertification
                ? 'Update Certification'
                : 'Create Certification'}
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
