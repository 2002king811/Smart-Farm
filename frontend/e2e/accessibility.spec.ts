import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { signUpFarm } from './helpers';

/** WCAG 2.1 AA checks (contrast ≥ 4.5:1, labels, roles, keyboard) on the main screens. */
const PAGES = [
  '/dashboard',
  '/livestock',
  '/health',
  '/calendar',
  '/activities',
  '/notifications',
  '/reports',
  '/settings/profile',
];

test('main screens have no serious accessibility problems', async ({ page }) => {
  await signUpFarm(page, 'Access Farm');
  const problems: string[] = [];
  for (const path of PAGES) {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    for (const v of result.violations.filter((x) => x.impact === 'serious' || x.impact === 'critical')) {
      problems.push(
        `${path}: ${v.id} – ${v.help} (${v.nodes
          .map((n) => n.target.join(' '))
          .slice(0, 3)
          .join(', ')})`,
      );
    }
  }
  expect(problems).toEqual([]);
});
