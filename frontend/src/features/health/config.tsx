import type { ReactNode } from 'react';

import { StatusBadge } from '@/components/StatusBadge';
import { formatDate } from '@/features/livestock/format';

/** One health record type: its API path, table columns and form fields. */
export type FieldType =
  | 'text'
  | 'textarea'
  | 'date'
  | 'number'
  | 'select'
  | 'animal'
  | 'group'
  | 'animals'
  | 'vaccine'
  | 'medicine'
  | 'money'
  | 'feed'
  | 'location'
  | 'checkbox';

export interface Field {
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
  options?: readonly (readonly [string, string])[];
  hint?: string;
  /** For medicine pickers: limit to these medicine types. */
  medicineTypes?: string[];
  /** Form value when the form opens. */
  initial?: string;
}

export type Row = Record<string, unknown> & { id: string };

export interface Column {
  label: string;
  render: (row: Row, fmt: string) => ReactNode;
  /** Hidden when the list is already about one animal. */
  subject?: boolean;
}

export interface RecordType {
  key: string;
  path: string;
  title: string;
  singular: string;
  empty: string;
  columns: Column[];
  fields: Field[];
  /** Filter that ties the list to one animal (profile tabs). */
  animalParam?: string;
  /** Permission module (default "health") and the action needed to add a record. */
  module?: 'health' | 'breeding' | 'nutrition';
  createAction?: string;
  /** Animal picker limited to one sex (e.g. deaths: any; matings: does). */
  animalSex?: 'female' | 'male';
}

export const DISEASES = [
  ['clostridial', 'Clostridial'],
  ['ppr', 'PPR'],
  ['goat_pox', 'Goat Pox'],
  ['brucellosis', 'Brucellosis'],
  ['anthrax', 'Anthrax'],
  ['ccpp', 'CCPP'],
  ['fmd', 'FMD'],
  ['other', 'Other'],
] as const;

export const ROUTES = [
  ['sc', 'Subcutaneous (SC)'],
  ['im', 'Intramuscular (IM)'],
  ['oral', 'Oral'],
  ['intranasal', 'Intranasal'],
  ['topical', 'Topical / pour-on'],
  ['other', 'Other'],
] as const;

const DONE = [
  ['completed', 'Completed'],
  ['missed', 'Missed'],
] as const;

const str = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v));
const date = (key: string) => (r: Row, fmt: string) => formatDate(r[key] as string | null, fmt);
const subject = (r: Row) => str(r.animal_label ?? r.group_label ?? 'Whole herd');
const badge = (key: string) => (r: Row) => <StatusBadge status={r[key] as string} />;

export const RECORD_TYPES: RecordType[] = [
  {
    key: 'vaccinations',
    path: '/vaccinations',
    title: 'Vaccinations',
    singular: 'vaccination',
    empty: 'No vaccinations recorded yet.',
    animalParam: 'animal',
    columns: [
      { label: 'Date', render: date('date') },
      { label: 'Animal / group', render: subject, subject: true },
      { label: 'Vaccine', render: (r) => str(r.vaccine_label) },
      { label: 'Next due', render: date('next_due_date') },
      { label: 'Status', render: badge('status') },
      { label: 'Given by', render: (r) => str(r.administered_by || r.vet_officer) },
    ],
    fields: [
      {
        name: 'animal',
        label: 'Animal',
        type: 'animal',
        hint: 'Leave animal and group empty for the whole herd.',
      },
      { name: 'group', label: 'Or a group', type: 'group' },
      { name: 'vaccine', label: 'Vaccine', type: 'vaccine' },
      { name: 'vaccine_name', label: 'Or vaccine name', type: 'text' },
      { name: 'disease_category', label: 'Disease', type: 'select', options: DISEASES },
      { name: 'date', label: 'Date given', type: 'date', required: true },
      { name: 'batch_number', label: 'Batch number', type: 'text' },
      { name: 'dosage', label: 'Dosage', type: 'text' },
      { name: 'route', label: 'Route', type: 'select', options: ROUTES },
      { name: 'administered_by', label: 'Given by', type: 'text' },
      { name: 'vet_officer', label: 'Vet officer', type: 'text' },
      {
        name: 'next_due_date',
        label: 'Next due date',
        type: 'date',
        hint: 'Adds a reminder to the health calendar.',
      },
      { name: 'status', label: 'Status', type: 'select', options: DONE, initial: 'completed' },
      { name: 'notes', label: 'Notes', type: 'textarea' },
    ],
  },
  {
    key: 'dewormings',
    path: '/dewormings',
    title: 'Deworming',
    singular: 'deworming',
    empty: 'No deworming recorded yet.',
    animalParam: 'animal',
    columns: [
      { label: 'Date', render: date('date') },
      { label: 'Animal / group', render: subject, subject: true },
      { label: 'Product', render: (r) => str(r.product_label) },
      { label: 'Dosage', render: (r) => str(r.dosage) },
      { label: 'Next due', render: date('next_due_date') },
      { label: 'Status', render: badge('status') },
    ],
    fields: [
      {
        name: 'animal',
        label: 'Animal',
        type: 'animal',
        hint: 'Leave animal and group empty for the whole herd.',
      },
      { name: 'group', label: 'Or a group', type: 'group' },
      { name: 'product', label: 'Dewormer', type: 'medicine', medicineTypes: ['dewormer'] },
      { name: 'product_name', label: 'Or product name', type: 'text' },
      { name: 'date', label: 'Date', type: 'date', required: true },
      { name: 'dosage', label: 'Dosage', type: 'text' },
      { name: 'administered_by', label: 'Given by', type: 'text' },
      {
        name: 'next_due_date',
        label: 'Next due date',
        type: 'date',
        hint: 'Adds a reminder to the health calendar.',
      },
      { name: 'status', label: 'Status', type: 'select', options: DONE, initial: 'completed' },
      { name: 'notes', label: 'Notes', type: 'textarea' },
    ],
  },
  {
    key: 'treatments',
    path: '/treatments',
    title: 'Treatments',
    singular: 'treatment',
    empty: 'No treatments recorded yet.',
    animalParam: 'animal',
    columns: [
      { label: 'Date', render: date('date') },
      { label: 'Animal', render: subject, subject: true },
      { label: 'Diagnosis', render: (r) => str(r.diagnosis) },
      { label: 'Medication', render: (r) => str(r.medication_label) },
      { label: 'Status', render: badge('status') },
      { label: 'Follow-up', render: date('follow_up_date') },
      { label: 'Withdrawal until', render: date('withdrawal_until') },
    ],
    fields: [
      { name: 'animal', label: 'Animal', type: 'animal', required: true },
      { name: 'date', label: 'Date', type: 'date', required: true },
      { name: 'diagnosis', label: 'Diagnosis', type: 'text', required: true },
      { name: 'symptoms', label: 'Symptoms', type: 'textarea' },
      { name: 'treatment', label: 'Treatment given', type: 'textarea' },
      { name: 'medication', label: 'Medication', type: 'medicine' },
      { name: 'medication_name', label: 'Or medication name', type: 'text' },
      { name: 'dosage', label: 'Dosage', type: 'text' },
      { name: 'route', label: 'Route', type: 'select', options: ROUTES },
      { name: 'responsible_person', label: 'Responsible person', type: 'text' },
      { name: 'vet_officer', label: 'Vet officer', type: 'text' },
      {
        name: 'follow_up_date',
        label: 'Follow-up date',
        type: 'date',
        hint: 'Adds a follow-up to the health calendar.',
      },
      {
        name: 'withdrawal_until',
        label: 'Withdrawal until',
        type: 'date',
        hint: 'Filled from the medicine if left empty.',
      },
      {
        name: 'status',
        label: 'Status',
        type: 'select',
        options: [
          ['ongoing', 'Ongoing'],
          ['resolved', 'Resolved'],
        ],
        initial: 'ongoing',
      },
      { name: 'notes', label: 'Notes', type: 'textarea' },
    ],
  },
  {
    key: 'observations',
    path: '/observations',
    title: 'Disease monitoring',
    singular: 'observation',
    empty: 'No observations recorded yet.',
    animalParam: 'animal',
    columns: [
      { label: 'Date', render: date('date') },
      { label: 'Animal', render: subject, subject: true },
      { label: 'Symptoms', render: (r) => str(r.symptoms) },
      { label: 'Temp (°C)', render: (r) => str(r.temperature_c) },
      { label: 'Severity', render: badge('severity') },
      { label: 'Suspected', render: (r) => str(r.suspected_disease) },
    ],
    fields: [
      { name: 'animal', label: 'Animal', type: 'animal', required: true },
      { name: 'date', label: 'Date', type: 'date', required: true },
      { name: 'symptoms', label: 'What did you see?', type: 'textarea', required: true },
      {
        name: 'temperature_c',
        label: 'Temperature (°C)',
        type: 'number',
        hint: 'Normal for goats: 38.5–40 °C.',
      },
      {
        name: 'severity',
        label: 'Severity',
        type: 'select',
        options: [
          ['mild', 'Mild'],
          ['moderate', 'Moderate'],
          ['severe', 'Severe'],
        ],
        initial: 'mild',
      },
      { name: 'suspected_disease', label: 'Suspected disease', type: 'text' },
      { name: 'observed_by', label: 'Observed by', type: 'text' },
      { name: 'action_taken', label: 'Action taken', type: 'textarea' },
      { name: 'notes', label: 'Notes', type: 'textarea' },
    ],
  },
  {
    key: 'vet-visits',
    path: '/vet-visits',
    title: 'Vet visits',
    singular: 'vet visit',
    empty: 'No vet visits recorded yet.',
    animalParam: 'animals',
    columns: [
      { label: 'Date', render: date('date') },
      { label: 'Vet', render: (r) => str(r.vet_name) },
      { label: 'Reason', render: (r) => str(r.reason) },
      {
        label: 'Animals',
        render: (r) => ((r.animal_labels as string[]) ?? []).join(', ') || 'Herd',
        subject: true,
      },
      { label: 'Next visit', render: date('next_visit_date') },
    ],
    fields: [
      { name: 'date', label: 'Date', type: 'date', required: true },
      { name: 'vet_name', label: 'Vet', type: 'text', required: true },
      { name: 'reason', label: 'Reason', type: 'text', required: true },
      { name: 'animals', label: 'Animals seen', type: 'animals' },
      { name: 'findings', label: 'Findings', type: 'textarea' },
      { name: 'recommendations', label: 'Recommendations', type: 'textarea' },
      {
        name: 'next_visit_date',
        label: 'Next visit',
        type: 'date',
        hint: 'Adds the visit to the health calendar.',
      },
      { name: 'cost_cents', label: 'Cost', type: 'money' },
      { name: 'notes', label: 'Notes', type: 'textarea' },
    ],
  },
  {
    key: 'inspections',
    path: '/inspections',
    title: 'Inspections',
    singular: 'inspection',
    empty: 'No inspections recorded yet.',
    columns: [
      { label: 'Date', render: date('date') },
      { label: 'Inspector', render: (r) => str(r.inspector) },
      { label: 'Result', render: badge('result') },
      { label: 'Score', render: (r) => (r.score ? `${r.score}/10` : '—') },
      { label: 'Animals inspected', render: (r) => str(r.animals_inspected) },
      { label: 'Next inspection', render: date('next_inspection_date') },
    ],
    fields: [
      { name: 'date', label: 'Date', type: 'date', required: true },
      { name: 'inspector', label: 'Inspector', type: 'text', required: true },
      { name: 'group', label: 'Group (optional)', type: 'group' },
      { name: 'animals_inspected', label: 'Animals inspected', type: 'number' },
      {
        name: 'result',
        label: 'Result',
        type: 'select',
        options: [
          ['good', 'Good'],
          ['needs_attention', 'Needs attention'],
          ['poor', 'Poor'],
        ],
        initial: 'good',
      },
      {
        name: 'score',
        label: 'Score (1–10)',
        type: 'select',
        options: Array.from({ length: 10 }, (_, i) => [String(i + 1), String(i + 1)] as const),
      },
      { name: 'findings', label: 'Findings', type: 'textarea' },
      {
        name: 'next_inspection_date',
        label: 'Next inspection',
        type: 'date',
        hint: 'Adds it to the health calendar.',
      },
      { name: 'notes', label: 'Notes', type: 'textarea' },
    ],
  },
  {
    key: 'parasite-control',
    path: '/parasite-control',
    title: 'Parasite control',
    singular: 'parasite control',
    empty: 'No parasite control recorded yet.',
    columns: [
      { label: 'Date', render: date('date') },
      { label: 'Method', render: (r) => str(PARASITE_METHODS.find(([v]) => v === r.method)?.[1]) },
      { label: 'Target', render: (r) => str(r.target) },
      { label: 'Product', render: (r) => str(r.product_label) },
      { label: 'Next due', render: date('next_due_date') },
    ],
    fields: [
      { name: 'date', label: 'Date', type: 'date', required: true },
      { name: 'method', label: 'Method', type: 'select', required: true, options: [] },
      { name: 'target', label: 'Target', type: 'text', required: true, hint: 'Ticks, mites, lice, flies…' },
      { name: 'product', label: 'Product', type: 'medicine', medicineTypes: ['acaricide'] },
      { name: 'product_name', label: 'Or product name', type: 'text' },
      { name: 'group', label: 'Group (optional)', type: 'group' },
      { name: 'administered_by', label: 'Done by', type: 'text' },
      {
        name: 'next_due_date',
        label: 'Next due date',
        type: 'date',
        hint: 'Adds a reminder to the health calendar.',
      },
      { name: 'notes', label: 'Notes', type: 'textarea' },
    ],
  },
];

export const PARASITE_METHODS = [
  ['dipping', 'Dipping'],
  ['spraying', 'Spraying'],
  ['pour_on', 'Pour-on'],
  ['injection', 'Injection'],
  ['environment', 'Pen / pasture treatment'],
] as const;

// Fill in the method options (declared after use above).
RECORD_TYPES.find((t) => t.key === 'parasite-control')!.fields.find((f) => f.name === 'method')!.options =
  PARASITE_METHODS;

export function recordType(key: string): RecordType {
  const t = RECORD_TYPES.find((r) => r.key === key);
  if (!t) throw new Error(`Unknown record type ${key}`);
  return t;
}
