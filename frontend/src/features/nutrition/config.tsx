import { StatusBadge } from '@/components/StatusBadge';
import type { RecordType, Row } from '@/features/health/config';
import { formatDate } from '@/features/livestock/format';

const str = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v));
const date = (key: string) => (r: Row, fmt: string) => formatDate(r[key] as string | null, fmt);
const subject = (r: Row) => str(r.animal_label ?? r.group_label ?? 'Whole herd');

export const FEEDING: RecordType = {
  key: 'feeding',
  path: '/feeding-records',
  title: 'Feeding',
  singular: 'feeding',
  empty: 'No feeding recorded yet.',
  module: 'nutrition',
  createAction: 'record_feeding',
  columns: [
    { label: 'Date', render: date('date') },
    { label: 'Feed', render: (r) => str(r.feed_item_name) },
    { label: 'Quantity', render: (r) => `${Number(r.quantity)} ${r.unit}` },
    { label: 'Group / location', render: (r) => str(r.group_label ?? r.location_label ?? 'Whole herd') },
    { label: 'Animals fed', render: (r) => str(r.animals_fed) },
    { label: 'By', render: (r) => str(r.responsible || r.recorded_by) },
  ],
  fields: [
    { name: 'feed_item', label: 'Feed', type: 'feed', required: true },
    { name: 'quantity', label: 'Quantity given', type: 'number', required: true, hint: 'Taken from stock.' },
    { name: 'date', label: 'Date', type: 'date', required: true },
    { name: 'group', label: 'Group', type: 'group' },
    { name: 'location', label: 'Location', type: 'location' },
    { name: 'animals_fed', label: 'Number of animals fed', type: 'number' },
    { name: 'responsible', label: 'Fed by', type: 'text' },
    { name: 'notes', label: 'Notes', type: 'text' },
  ],
};

export const ASSESSMENTS: RecordType = {
  key: 'assessments',
  path: '/nutrition-assessments',
  title: 'Assessments',
  singular: 'nutrition assessment',
  empty: 'No nutrition assessments yet.',
  module: 'nutrition',
  animalParam: 'animal',
  columns: [
    { label: 'Date', render: date('date') },
    { label: 'Animal / group', render: subject, subject: true },
    { label: 'Body condition', render: (r) => str(r.body_condition_score) },
    { label: 'Pasture', render: (r) => str(r.pasture_condition) },
    { label: 'Findings', render: (r) => str(r.findings) },
    { label: 'Next', render: date('next_assessment_date') },
  ],
  fields: [
    {
      name: 'animal',
      label: 'Animal',
      type: 'animal',
      hint: 'Leave animal and group empty for the whole herd.',
    },
    { name: 'group', label: 'Or a group', type: 'group' },
    { name: 'date', label: 'Date', type: 'date', required: true },
    {
      name: 'body_condition_score',
      label: 'Body condition score',
      type: 'select',
      options: ['1', '1.5', '2', '2.5', '3', '3.5', '4', '4.5', '5'].map((v) => [v, v] as const),
    },
    {
      name: 'pasture_condition',
      label: 'Pasture condition',
      type: 'select',
      options: [
        ['good', 'Good'],
        ['fair', 'Fair'],
        ['poor', 'Poor'],
      ],
    },
    { name: 'assessor', label: 'Assessed by', type: 'text' },
    {
      name: 'next_assessment_date',
      label: 'Next assessment',
      type: 'date',
      hint: 'Adds it to the health calendar.',
    },
    { name: 'findings', label: 'Findings', type: 'textarea' },
    { name: 'recommendations', label: 'Recommendations', type: 'textarea' },
  ],
};

export const SUPPLEMENTS: RecordType = {
  key: 'supplements',
  path: '/supplementation',
  title: 'Supplements',
  singular: 'supplement',
  empty: 'No supplements recorded yet.',
  module: 'nutrition',
  animalParam: 'animal',
  columns: [
    { label: 'Date', render: date('date') },
    { label: 'Supplement', render: (r) => str(r.supplement) },
    { label: 'Animal / group', render: subject, subject: true },
    { label: 'Dosage', render: (r) => str(r.dosage || (r.quantity ? Number(r.quantity) : '')) },
    { label: 'Reason', render: (r) => str(r.reason) },
  ],
  fields: [
    {
      name: 'supplement',
      label: 'Supplement',
      type: 'text',
      required: true,
      hint: 'Mineral lick, vitamins, molasses…',
    },
    { name: 'date', label: 'Date', type: 'date', required: true },
    { name: 'animal', label: 'Animal', type: 'animal' },
    { name: 'group', label: 'Or a group', type: 'group' },
    { name: 'feed_item', label: 'Take from stock', type: 'feed' },
    { name: 'quantity', label: 'Quantity from stock', type: 'number' },
    { name: 'dosage', label: 'Dosage', type: 'text' },
    { name: 'reason', label: 'Reason', type: 'text' },
    { name: 'given_by', label: 'Given by', type: 'text' },
    { name: 'notes', label: 'Notes', type: 'textarea' },
  ],
};

export const HYGIENE: RecordType = {
  key: 'hygiene',
  path: '/water-hygiene',
  title: 'Water & hygiene',
  singular: 'water & hygiene check',
  empty: 'No checks recorded yet.',
  module: 'nutrition',
  columns: [
    { label: 'Date', render: date('date') },
    { label: 'Location', render: (r) => str(r.location_label) },
    { label: 'Water source', render: (r) => str(r.water_source) },
    {
      label: 'Score',
      render: (r) => (
        <StatusBadge
          status={Number(r.score) >= 5 ? 'good' : Number(r.score) >= 3 ? 'needs_attention' : 'poor'}
          label={`${r.score}/5`}
        />
      ),
    },
    { label: 'Issues', render: (r) => str(r.issues) },
  ],
  fields: [
    { name: 'date', label: 'Date', type: 'date', required: true },
    { name: 'location', label: 'Location', type: 'location' },
    { name: 'water_source', label: 'Water source', type: 'text', hint: 'Borehole, tank, river…' },
    { name: 'checked_by', label: 'Checked by', type: 'text' },
    { name: 'water_available', label: 'Water available', type: 'checkbox' },
    { name: 'water_clean', label: 'Water clean', type: 'checkbox' },
    { name: 'troughs_clean', label: 'Troughs clean', type: 'checkbox' },
    { name: 'pen_clean', label: 'Pen clean', type: 'checkbox' },
    { name: 'bedding_dry', label: 'Bedding dry', type: 'checkbox' },
    { name: 'issues', label: 'Issues found', type: 'textarea' },
    { name: 'actions_taken', label: 'Actions taken', type: 'textarea' },
  ],
};
