import { useQueryClient } from '@tanstack/react-query';
import { MapPin, Users } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { api, ApiError } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { FormError, FormInput, FormSelect } from '@/components/forms';
import { LoadingState } from '@/components/LoadingState';
import { Modal } from '@/components/Modal';
import page from '@/components/Page.module.css';
import { useToast } from '@/components/Toast';

import { useGroups, useLocations, type Group, type Location } from './api';

const LOCATION_TYPES = [
  ['paddock', 'Paddock'],
  ['pen', 'Pen'],
  ['isolation', 'Isolation'],
  ['quarantine', 'Quarantine'],
  ['other', 'Other'],
] as const;

type Kind = 'locations' | 'animal-groups';
type Item = Partial<Location & Group> & { id?: string };

export default function SetupPage() {
  const locations = useLocations();
  const groups = useGroups();
  const [editing, setEditing] = useState<{ kind: Kind; item: Item } | null>(null);
  return (
    <>
      <div className={page.header}>
        <div>
          <h2>Locations &amp; groups</h2>
          <p>
            Where animals are kept, and how you group them. <Link to="/livestock">Back to the register</Link>
          </p>
        </div>
      </div>
      <div style={{ display: 'grid', gap: 'var(--space-5)' }}>
        <ListCard
          title="Locations"
          icon={MapPin}
          kind="locations"
          rows={locations.data}
          loading={locations.isPending}
          describe={(l) =>
            `${LOCATION_TYPES.find(([v]) => v === l.type)?.[1] ?? ''}${l.capacity ? ` · capacity ${l.capacity}` : ''}`
          }
          onEdit={(item) => setEditing({ kind: 'locations', item })}
        />
        <ListCard
          title="Groups"
          icon={Users}
          kind="animal-groups"
          rows={groups.data}
          loading={groups.isPending}
          describe={(g) => g.description ?? ''}
          onEdit={(item) => setEditing({ kind: 'animal-groups', item })}
        />
      </div>
      {editing && <EditModal kind={editing.kind} item={editing.item} onClose={() => setEditing(null)} />}
    </>
  );
}

function ListCard({
  title,
  icon,
  kind,
  rows,
  loading,
  describe,
  onEdit,
}: {
  title: string;
  icon: typeof MapPin;
  kind: Kind;
  rows?: Item[];
  loading: boolean;
  describe: (row: Item) => string;
  onEdit: (row: Item) => void;
}) {
  return (
    <section className={page.card}>
      <div className={page.cardBody}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <h3>{title}</h3>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => onEdit(kind === 'locations' ? { type: 'pen' } : {})}
          >
            Add {kind === 'locations' ? 'location' : 'group'}
          </button>
        </div>
        {loading ? (
          <LoadingState />
        ) : !rows?.length ? (
          <EmptyState icon={icon} title={`No ${title.toLowerCase()} yet`} />
        ) : (
          <table className={page.table}>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Animals</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.name}</strong>
                    <span className={page.sub}>{describe(r)}</span>
                  </td>
                  <td>{r.animal_count}</td>
                  <td>
                    <div className={page.rowActions}>
                      <button
                        type="button"
                        className={page.small}
                        onClick={() => onEdit(r)}
                        aria-label={`Edit ${r.name}`}
                      >
                        Edit
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

function EditModal({ kind, item, onClose }: { kind: Kind; item: Item; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [values, setValues] = useState({
    name: item.name ?? '',
    type: item.type ?? 'pen',
    capacity: item.capacity?.toString() ?? '',
    description: item.description ?? '',
  });
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const isLocation = kind === 'locations';
  const noun = isLocation ? 'location' : 'group';

  const save = async () => {
    setBusy(true);
    setErrors({});
    const body = isLocation
      ? {
          name: values.name,
          type: values.type,
          capacity: values.capacity ? Number(values.capacity) : null,
          description: values.description,
        }
      : { name: values.name, description: values.description };
    try {
      await api(item.id ? `/${kind}/${item.id}` : `/${kind}`, { method: item.id ? 'PATCH' : 'POST', body });
      await qc.invalidateQueries({ queryKey: [kind] });
      toast.success(`${values.name} saved.`);
      onClose();
    } catch (err) {
      setErrors(err instanceof ApiError ? err.errors : { detail: ['Could not save.'] });
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    try {
      await api(`/${kind}/${item.id}`, { method: 'DELETE' });
      await qc.invalidateQueries({ queryKey: [kind] });
      await qc.invalidateQueries({ queryKey: ['animals'] });
      toast.success(`${item.name} removed.`);
      onClose();
    } catch (err) {
      setErrors(err instanceof ApiError ? err.errors : { detail: ['Could not remove.'] });
    }
  };

  return (
    <Modal
      title={item.id ? `Edit ${item.name}` : `Add ${noun}`}
      open
      onClose={onClose}
      footer={
        <>
          {item.id && (
            <button
              type="button"
              className="btn btn-secondary"
              style={{ marginRight: 'auto', color: 'var(--tone-red-fg)' }}
              onClick={() => void remove()}
            >
              Remove
            </button>
          )}
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void save()}
            disabled={busy || !values.name.trim()}
          >
            Save
          </button>
        </>
      }
    >
      <FormError message={errors.detail?.[0]} />
      <FormInput
        label="Name"
        value={values.name}
        error={errors.name?.[0]}
        onChange={(e) => setValues({ ...values, name: e.target.value })}
      />
      {isLocation && (
        <div className={page.grid2}>
          <FormSelect
            label="Type"
            value={values.type}
            onChange={(e) => setValues({ ...values, type: e.target.value as typeof values.type })}
          >
            {LOCATION_TYPES.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </FormSelect>
          <FormInput
            label="Capacity (optional)"
            type="number"
            min={0}
            value={values.capacity}
            error={errors.capacity?.[0]}
            onChange={(e) => setValues({ ...values, capacity: e.target.value })}
          />
        </div>
      )}
      <FormInput
        label="Description (optional)"
        value={values.description}
        onChange={(e) => setValues({ ...values, description: e.target.value })}
      />
      {item.id && <p className={page.sub}>Removing it keeps the animals; they just lose this {noun}.</p>}
    </Modal>
  );
}
