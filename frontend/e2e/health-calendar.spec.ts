import { expect, test } from '@playwright/test';

import { signUpFarm } from './helpers';
import { manage } from './manage';

const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const inDays = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return iso(d);
};

/** Run the overdue job as if it were a later day (the scheduled job does this at 00:05). */
function markOverdue(asOf: string) {
  manage('mark_overdue', '--as-of', asOf);
}

/** Phase 4 "done when": a vaccination with a next due date appears on the calendar and turns
 * Overdue if missed. */
test('vaccination due date appears on the calendar and turns overdue when missed', async ({ page }) => {
  await signUpFarm(page, 'YPA FARM');

  await page.goto('/livestock/new');
  await page.getByLabel('Name', { exact: true }).fill('Simba');
  await page.getByLabel('Male', { exact: true }).check();
  await page.getByLabel('Date of birth *').fill('2024-03-15');
  await page.getByRole('button', { name: 'Register animal' }).click();
  await expect(page.getByRole('heading', { name: 'YPA-001 · Simba' })).toBeVisible();

  // Record the vaccination from the animal profile, choosing the vaccine from the list.
  await page.getByRole('tab', { name: 'Vaccinations' }).click();
  await page.getByRole('button', { name: 'Record vaccination' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Vaccine', { exact: true }).selectOption({ label: 'PPR vaccine' });
  await expect(dialog.getByLabel('Disease')).toHaveValue('ppr');
  await dialog.getByLabel('Next due date').fill(inDays(5));
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('The vaccination was recorded.')).toBeVisible();
  await expect(page.getByRole('cell', { name: 'PPR vaccine' })).toBeVisible();

  // It is on the health calendar as a pending task.
  await page.getByRole('link', { name: 'Health Calendar' }).click();
  await page.getByRole('button', { name: 'Agenda' }).click();
  const item = page.getByRole('button', { name: /Vaccination due: PPR vaccine – YPA-001/ });
  await expect(item).toBeVisible();
  await expect(item.getByText('Pending')).toBeVisible();

  // Six days later the overdue job runs; the task is Overdue on the calendar and in the list.
  markOverdue(inDays(6));
  await page.goto('/activities');
  await page.getByRole('tab', { name: 'Overdue' }).click();
  await expect(page.getByRole('button', { name: 'Vaccination due: PPR vaccine – YPA-001' })).toBeVisible();
  await page.getByRole('button', { name: 'Vaccination due: PPR vaccine – YPA-001' }).click();
  const detail = page.getByRole('dialog');
  await expect(detail.getByText('Overdue').first()).toBeVisible();
  await expect(detail.getByText('Passed its date without being completed')).toBeVisible();

  // Completing it records who did it.
  await detail.getByRole('button', { name: 'Mark complete' }).click();
  await expect(page.getByText('Marked as completed.')).toBeVisible();

  // The 2027 plan adds 23 activities; January shows the opening assessment.
  await page.goto('/calendar');
  await page.getByRole('button', { name: 'Add the 23 activities' }).click();
  await expect(page.getByText('23 planned activities added to the calendar.')).toBeVisible();
  await page.getByRole('button', { name: 'Month' }).click();
  for (let i = 0; i < 24 && !(await page.getByRole('heading', { name: 'January 2027' }).isVisible()); i++) {
    await page.getByRole('button', { name: 'Next' }).click();
  }
  await expect(page.getByRole('button', { name: /Opening herd health assessment/ })).toBeVisible();
});

test('a treatment puts the animal under treatment with a withdrawal warning', async ({ page }) => {
  await signUpFarm(page, 'YPA FARM');
  await page.goto('/livestock/new');
  await page.getByLabel('Name', { exact: true }).fill('Zawadi');
  await page.getByLabel('Female', { exact: true }).check();
  await page.getByLabel('Date of birth *').fill('2024-07-19');
  await page.getByRole('button', { name: 'Register animal' }).click();
  await page.getByRole('tab', { name: 'Health' }).click();
  await page.getByRole('button', { name: 'Record treatment' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Diagnosis *').fill('Pneumonia');
  await dialog.getByLabel('Medication', { exact: true }).selectOption({ label: 'Oxytetracycline LA' });
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('The treatment was recorded.')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Under Treatment').first()).toBeVisible();
  await expect(page.getByText(/Do not sell or milk until/)).toBeVisible();
  await page.getByRole('tab', { name: 'Health' }).click();
  await page.getByRole('button', { name: 'Resolve' }).click();
  await expect(page.getByText('Treatment resolved.')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Healthy').first()).toBeVisible();
});
