import { StatusBadge } from '@/components/StatusBadge';
import type { RecordType, Row } from '@/features/health/config';
import { formatDate } from '@/features/livestock/format';

const str = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v));

export const DEATH_CAUSES = [
  ['disease', 'Disease'],
  ['birth', 'Birth complications'],
  ['predator', 'Predator'],
  ['accident', 'Accident / injury'],
  ['poisoning', 'Poisoning'],
  ['malnutrition', 'Malnutrition'],
  ['old_age', 'Old age'],
  ['unknown', 'Unknown'],
] as const;

export const MORTALITY: RecordType = {
  key: 'mortality',
  path: '/mortality',
  title: 'Mortality',
  singular: 'death',
  empty: 'No deaths recorded.',
  module: 'breeding',
  animalParam: 'animal',
  columns: [
    { label: 'Date', render: (r: Row, fmt) => formatDate(r.date as string, fmt) },
    { label: 'Animal', render: (r) => str(r.animal_label), subject: true },
    {
      label: 'Age',
      render: (r) => (r.age_at_death_months === null ? '—' : `${r.age_at_death_months} months`),
    },
    { label: 'Cause', render: (r) => str(DEATH_CAUSES.find(([v]) => v === r.cause_category)?.[1]) },
    { label: 'Details', render: (r) => str(r.cause) },
    { label: 'Disposal', render: (r) => str(r.disposal).replace('_', ' ') },
  ],
  fields: [
    { name: 'animal', label: 'Animal', type: 'animal', required: true },
    { name: 'date', label: 'Date of death', type: 'date', required: true },
    { name: 'cause_category', label: 'Cause', type: 'select', options: DEATH_CAUSES, initial: 'unknown' },
    { name: 'cause', label: 'Details', type: 'text', hint: 'e.g. suspected pneumonia' },
    {
      name: 'disposal',
      label: 'Disposal',
      type: 'select',
      initial: 'burial',
      options: [
        ['burial', 'Burial'],
        ['burning', 'Burning'],
        ['post_mortem', 'Sent for post-mortem'],
        ['other', 'Other'],
      ],
    },
    { name: 'notes', label: 'Notes', type: 'textarea' },
  ],
};

export const MATING_STATUS = (r: Row) =>
  r.status === 'active' ? (
    <StatusBadge status={r.pregnancy_status as string} />
  ) : (
    <StatusBadge status={r.status as string} />
  );
