import { can, scopeOf } from './permissions';

describe('role table mirror', () => {
  it('matches section 3 of the spec', () => {
    expect(can('administrator', 'users')).toBe(true);
    expect(can('farm_manager', 'users')).toBe(false);
    expect(can('farm_manager', 'settings')).toBe(false);
    expect(can('farm_manager', 'reports')).toBe(true);
    expect(can('livestock_attendant', 'reports')).toBe(false);
    expect(can('livestock_attendant', 'livestock', 'create')).toBe(true);
    expect(can('livestock_attendant', 'livestock', 'delete')).toBe(false);
    expect(can('livestock_attendant', 'activities', 'complete')).toBe(true);
    expect(scopeOf('livestock_attendant', 'activities')).toBe('own');
    expect(can(undefined, 'dashboard')).toBe(false);
  });
});
