import styles from './StatusBadge.module.css';

/**
 * The single status → colour mapping for the whole app. Every status pill uses this
 * component; never colour a status anywhere else. Keys are the API values; labels are the
 * exact prototype wording.
 */
export type Tone = 'green' | 'amber' | 'red' | 'blue' | 'purple' | 'pink' | 'grey';

interface StatusDef {
  label: string;
  tone: Tone;
}

export const STATUS_MAP: Record<string, StatusDef> = {
  // Animal health status
  healthy: { label: 'Healthy', tone: 'green' },
  under_treatment: { label: 'Under Treatment', tone: 'amber' },
  sick: { label: 'Sick', tone: 'red' },
  quarantined: { label: 'Quarantined', tone: 'purple' },
  pregnant: { label: 'Pregnant', tone: 'pink' },
  monitoring: { label: 'Monitoring', tone: 'blue' },
  // Activities and tasks
  pending: { label: 'Pending', tone: 'amber' },
  in_progress: { label: 'In Progress', tone: 'blue' },
  completed: { label: 'Completed', tone: 'green' },
  overdue: { label: 'Overdue', tone: 'red' },
  cancelled: { label: 'Cancelled', tone: 'grey' },
  // Priority
  high: { label: 'High', tone: 'red' },
  medium: { label: 'Medium', tone: 'amber' },
  low: { label: 'Low', tone: 'grey' },
  // Treatments
  ongoing: { label: 'Ongoing', tone: 'amber' },
  resolved: { label: 'Resolved', tone: 'green' },
  // Pregnancy
  awaiting_scan: { label: 'Awaiting scan', tone: 'amber' },
  confirmed: { label: 'Confirmed', tone: 'green' },
  not_pregnant: { label: 'Not pregnant', tone: 'grey' },
  kidded: { label: 'Kidded', tone: 'green' },
  // Users and farms
  active: { label: 'Active', tone: 'green' },
  inactive: { label: 'Inactive', tone: 'grey' },
  suspended: { label: 'Suspended', tone: 'red' },
  // Message delivery
  queued: { label: 'Queued', tone: 'grey' },
  sent: { label: 'Sent', tone: 'blue' },
  delivered: { label: 'Delivered', tone: 'green' },
  read: { label: 'Read', tone: 'green' },
  failed: { label: 'Failed', tone: 'red' },
};

export function statusDef(status: string): StatusDef {
  return STATUS_MAP[status] ?? { label: status.replace(/_/g, ' '), tone: 'grey' };
}

interface Props {
  status: string;
  /** Overrides the label (e.g. a translated one); the colour still comes from the status. */
  label?: string;
}

export function StatusBadge({ status, label }: Props) {
  const def = statusDef(status);
  return (
    <span className={`${styles.badge} ${styles[def.tone]}`} data-status={status} data-tone={def.tone}>
      {label ?? def.label}
    </span>
  );
}
