import { devices, expect, test } from '@playwright/test';

import { manage } from './manage';

/** Phase 8 "done when": an attendant completes tasks with data switched off, and they sync
 * when it is back on. Uses the demo farm (python manage.py seed_demo). */

function seedDemo() {
  manage('seed_demo', '--reset', ...(process.env.E2E_MANAGE ? ['--force'] : []));
}

test.use({ ...devices['Pixel 5'] });

test('attendant completes tasks offline; they sync when the phone is back online', async ({
  page,
  context,
}) => {
  seedDemo();
  await page.goto('/login');
  await page.getByLabel('Username, email or phone').fill('peter.otieno@ypafarm.example.com');
  await page.getByLabel('Password', { exact: true }).fill('Demo-Farm-2026');
  await page.getByRole('button', { name: 'Log in' }).click();

  // The attendant's phone layout: bottom navigation.
  const nav = page.getByRole('navigation', { name: /main|bottom/i }).last();
  await expect(nav.getByRole('link', { name: 'Tasks' })).toBeVisible();
  await nav.getByRole('link', { name: 'Tasks' }).click();
  const dip = page.getByRole('button', { name: 'Dip the herd (tick control)' }).first();
  await expect(dip).toBeVisible();
  const trim = page.getByRole('button', { name: 'Follow-up treatment – Furaha' });
  await expect(trim).toBeVisible();

  // Data off.
  await context.setOffline(true);
  for (const task of [dip, trim]) {
    await task.click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('button', { name: 'Mark complete' }).click();
    await expect(
      page.getByText('Saved on this phone. It will sync when you are back online.').first(),
    ).toBeVisible();
    await dialog.getByRole('button', { name: /close/i }).first().click();
  }
  await expect(page.getByText(/You are offline/)).toBeVisible();
  await expect(page.getByText('Waiting to sync (2)')).toBeVisible();

  // Data back on: the queue empties and the server has both tasks completed.
  await context.setOffline(false);
  await page.evaluate("window.dispatchEvent(new Event('online'))");
  await expect(page.getByText(/Waiting to sync/)).toHaveCount(0, { timeout: 20_000 });
  await page.reload();
  await page.getByRole('tab', { name: 'Completed' }).click();
  await expect(page.getByRole('button', { name: 'Dip the herd (tick control)' }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Follow-up treatment – Furaha' })).toBeVisible();
});
