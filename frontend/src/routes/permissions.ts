import matrix from './permissions.json';

/**
 * Mirror of the backend role table (backend/apps/core/permissions_matrix.json). CI fails if the
 * two copies differ; regenerate with `python manage.py export_permissions`.
 * The UI hides what a role cannot use rather than showing it disabled.
 */
export type Role = 'administrator' | 'farm_manager' | 'livestock_attendant';
export type Module = keyof typeof matrix.modules;

interface Rule {
  actions: '*' | string[];
  scope: 'all' | 'own';
}
type RoleRules = Partial<Record<Module, Rule>>;

const roles = matrix.roles as Record<Role, RoleRules>;

export const ROLE_LABELS: Record<Role, string> = {
  administrator: 'Administrator',
  farm_manager: 'Farm Manager',
  livestock_attendant: 'Livestock Attendant',
};

export function can(role: Role | undefined, module: Module, action = 'view'): boolean {
  if (!role) return false;
  const rule = roles[role]?.[module];
  if (!rule) return false;
  return rule.actions === '*' || rule.actions.includes(action);
}

export function scopeOf(role: Role | undefined, module: Module): 'all' | 'own' | null {
  if (!role) return null;
  return roles[role]?.[module]?.scope ?? null;
}
