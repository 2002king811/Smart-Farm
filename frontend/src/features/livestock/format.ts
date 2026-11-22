/** Formatting that follows the farm's settings (date format, weight unit). */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function formatDate(value: string | null | undefined, pattern = 'DD MMM YYYY'): string {
  if (!value) return '—';
  let day = value.slice(0, 10);
  if (value.length > 10) {
    // A timestamp: show the local calendar day, not the UTC one.
    const t = new Date(value);
    day = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
  }
  const [y, m, d] = day.split('-').map(Number) as [number, number, number];
  const dd = String(d).padStart(2, '0');
  const mm = String(m).padStart(2, '0');
  switch (pattern) {
    case 'DD/MM/YYYY':
      return `${dd}/${mm}/${y}`;
    case 'MM/DD/YYYY':
      return `${mm}/${dd}/${y}`;
    case 'YYYY-MM-DD':
      return `${y}-${mm}-${dd}`;
    default:
      return `${dd} ${MONTHS[m - 1]} ${y}`;
  }
}

/** "2 yrs 3 mo", "5 mo", "12 days"; prefixed with "~" when the birth date is estimated. */
export function formatAge(dob: string | null | undefined, estimated = false, today = new Date()): string {
  if (!dob) return 'Unknown';
  const [y, m, d] = dob.split('-').map(Number) as [number, number, number];
  let months = (today.getFullYear() - y) * 12 + (today.getMonth() + 1 - m);
  if (today.getDate() < d) months -= 1;
  let text: string;
  if (months < 1) {
    const days = Math.max(0, Math.floor((today.getTime() - new Date(y, m - 1, d).getTime()) / 86_400_000));
    text = `${days} day${days === 1 ? '' : 's'}`;
  } else if (months < 12) {
    text = `${months} mo`;
  } else {
    const years = Math.floor(months / 12);
    const rest = months % 12;
    text = `${years} yr${years === 1 ? '' : 's'}${rest ? ` ${rest} mo` : ''}`;
  }
  return estimated ? `~${text}` : text;
}

export function formatWeight(kg: string | number | null | undefined, unit = 'kg'): string {
  if (kg === null || kg === undefined || kg === '') return '—';
  const value = Number(kg);
  return unit === 'lb' ? `${(value * 2.20462).toFixed(1)} lb` : `${value.toFixed(1)} kg`;
}

export const SPECIES = [
  ['goat', 'Goat'],
  ['sheep', 'Sheep'],
  ['dairy_cattle', 'Dairy cattle'],
  ['beef_cattle', 'Beef cattle'],
  ['poultry', 'Poultry'],
] as const;

export const BREEDS: Record<string, string[]> = {
  goat: [
    'Galla',
    'Boer',
    'Small East African',
    'Kenya Alpine',
    'Toggenburg',
    'Saanen',
    'Alpine',
    'Anglo-Nubian',
    'Crossbreed',
  ],
  sheep: ['Red Maasai', 'Dorper', 'Merino', 'Corriedale', 'Hampshire', 'Black Head Persian', 'Crossbreed'],
  dairy_cattle: ['Friesian', 'Ayrshire', 'Jersey', 'Guernsey', 'Crossbreed'],
  beef_cattle: ['Boran', 'Sahiwal', 'Hereford', 'Angus', 'Zebu', 'Crossbreed'],
  poultry: ['Kienyeji', 'Kuroiler', 'Kenbro', 'Layers', 'Broilers'],
};

export const HEALTH_STATUSES = [
  ['healthy', 'Healthy'],
  ['under_treatment', 'Under Treatment'],
  ['sick', 'Sick'],
  ['quarantined', 'Quarantined'],
  ['pregnant', 'Pregnant'],
  ['monitoring', 'Monitoring'],
] as const;

export const BREEDING_STATUSES = [
  ['open', 'Open'],
  ['served', 'Served'],
  ['pregnant', 'Pregnant'],
  ['lactating', 'Lactating'],
  ['dry', 'Dry'],
  ['breeding_male', 'Breeding male'],
  ['castrated', 'Castrated'],
  ['too_young', 'Too young'],
] as const;

export const SOURCES = [
  ['born_on_farm', 'Born on farm'],
  ['purchased', 'Purchased'],
  ['gift', 'Gift'],
  ['other', 'Other'],
] as const;

export const EXIT_REASONS = [
  ['sold', 'Sold'],
  ['died', 'Died'],
  ['culled', 'Culled'],
] as const;

export function labelOf(list: readonly (readonly [string, string])[], value?: string | null): string {
  return list.find(([v]) => v === value)?.[1] ?? value ?? '—';
}
