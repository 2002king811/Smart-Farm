import { formatAge, formatDate, formatWeight } from './format';

describe('livestock formatting', () => {
  const today = new Date(2026, 10, 21); // 21 Nov 2026

  it('formats ages like the register shows them', () => {
    expect(formatAge('2026-11-09', false, today)).toBe('12 days');
    expect(formatAge('2026-11-20', false, today)).toBe('1 day');
    expect(formatAge('2026-06-21', false, today)).toBe('5 mo');
    expect(formatAge('2025-11-21', false, today)).toBe('1 yr');
    expect(formatAge('2024-08-01', true, today)).toBe('~2 yrs 3 mo');
    expect(formatAge(null)).toBe('Unknown');
  });

  it('follows the farm date format and weight unit', () => {
    expect(formatDate('2027-01-05')).toBe('05 Jan 2027');
    expect(formatDate('2027-01-05', 'DD/MM/YYYY')).toBe('05/01/2027');
    expect(formatDate('2027-01-05T10:00:00Z', 'YYYY-MM-DD')).toBe('2027-01-05');
    expect(formatDate(null)).toBe('—');
    expect(formatWeight('31.5')).toBe('31.5 kg');
    expect(formatWeight(10, 'lb')).toBe('22.0 lb');
    expect(formatWeight(null)).toBe('—');
  });
});
