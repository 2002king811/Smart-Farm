import { expect, test } from '@playwright/test';

import { signUpFarm } from './helpers';

/** Phase 3 "done when": every action on the Livestock and Animal Profile screens persists. */
test('register, weigh, photograph, edit, move and exit animals; everything survives a reload', async ({
  page,
}) => {
  await signUpFarm(page, 'YPA FARM');

  // --- Register a doe with a known birth date ------------------------------------------------
  await page.getByRole('link', { name: 'Livestock' }).click();
  await expect(page.getByText('No animals yet')).toBeVisible();
  await page
    .getByRole('link', { name: /Register animal/ })
    .first()
    .click();
  await expect(page.getByLabel('Animal ID *')).toHaveValue('YPA-001');
  await page.getByLabel('Ear tag').fill('KE1001');
  await page.getByLabel('Name', { exact: true }).fill('Neema');
  await page.getByLabel('Breed', { exact: true }).fill('Galla');
  await page.getByLabel('Female', { exact: true }).check();
  await page.getByLabel('Date of birth *').fill('2024-03-15');
  await page.getByLabel('Location', { exact: true }).selectOption({ label: 'Night Pen' });
  await page.getByRole('button', { name: 'Register animal' }).click();
  await expect(page.getByRole('heading', { name: 'YPA-001 · Neema' })).toBeVisible();

  // --- Register a kid with an estimated age, its dam, and a photo --------------------------------
  await page.goto('/livestock/new');
  await expect(page.getByLabel('Animal ID *')).toHaveValue('YPA-002');
  await page.getByLabel('Name', { exact: true }).fill('Baraka');
  await page.getByLabel('Male', { exact: true }).check();
  await page.getByLabel('Estimate the age').check();
  await page.getByLabel('Estimated age (months) *').fill('2');
  await page.getByLabel('Dam (mother)').selectOption({ label: 'YPA-001 Neema' });
  await page.locator('input[type=file]').setInputFiles('e2e/fixtures/goat.png');
  await page.getByRole('button', { name: 'Register animal' }).click();
  await expect(page.getByRole('heading', { name: 'YPA-002 · Baraka' })).toBeVisible();
  await expect(page.getByRole('img', { name: 'YPA-002 Baraka' })).toBeVisible();

  // Duplicate ear tag is refused with the message under the field.
  await page.goto('/livestock/new');
  await page.getByLabel('Ear tag').fill('ke1001');
  await page.getByLabel('Female', { exact: true }).check();
  await page.getByLabel('Date of birth *').fill('2025-01-01');
  await page.getByRole('button', { name: 'Register animal' }).click();
  await expect(page.getByText('This ear tag is already used on this farm.')).toBeVisible();

  // --- Register: counts, filters, persistence -------------------------------------------------------
  await page.goto('/livestock');
  await expect(page.getByRole('link', { name: 'YPA-002 Baraka' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Kids (under 6 months)' })).toContainText('1');
  await page.getByLabel('Age', { exact: true }).selectOption('kid');
  await expect(page.getByRole('link', { name: 'YPA-001 Neema' })).toHaveCount(0);
  await page.getByLabel('Age', { exact: true }).selectOption('');

  // --- Profile: weight, edit (status + move), timeline -------------------------------------------
  await page.getByRole('link', { name: 'YPA-001 Neema' }).click();
  await page
    .getByRole('button', { name: /Record weight/ })
    .first()
    .click();
  await page.getByRole('dialog').getByLabel('Weight (kg)').fill('38.4');
  await page.getByRole('dialog').getByRole('button', { name: 'Save weight' }).click();
  await expect(page.getByText('Weight saved for YPA-001.')).toBeVisible();
  await page.getByRole('link', { name: 'Edit' }).click();
  await page.getByLabel('Health status').selectOption('sick');
  await page.getByLabel('Location', { exact: true }).selectOption({ label: 'Isolation Pen' });
  await page.getByLabel('Current condition').fill('Coughing, off feed');
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByText('YPA-001 is updated.')).toBeVisible();

  await page.reload();
  await expect(page.getByText('Sick').first()).toBeVisible();
  await expect(page.getByText('Isolation Pen').first()).toBeVisible();
  await expect(page.getByText('38.4 kg', { exact: false }).first()).toBeVisible();
  await expect(page.getByText('Coughing, off feed')).toBeVisible();
  await page.getByRole('tab', { name: 'Weight & Growth' }).click();
  await expect(page.getByRole('img', { name: /Weight chart with 1 records/ })).toBeVisible();
  await page.getByRole('tab', { name: 'Timeline' }).click();
  await expect(page.getByText('Moved to Isolation Pen')).toBeVisible();
  await expect(page.getByText('Health status: Sick')).toBeVisible();
  await expect(page.getByText('Weighed 38.40 kg')).toBeVisible();

  // --- Exit and undo ------------------------------------------------------------------------------
  await page.getByRole('button', { name: 'Sold / died / culled' }).click();
  await page.getByRole('dialog').getByLabel('Notes').fill('Sold at Nakuru market');
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Left the herd:' })).toBeVisible();
  await page.goto('/livestock');
  await expect(page.getByRole('link', { name: 'YPA-001 Neema' })).toHaveCount(0);
  await page.getByLabel('Show').selectOption('false');
  await expect(page.getByRole('link', { name: 'YPA-001 Neema' })).toBeVisible();

  // --- Locations & groups ---------------------------------------------------------------------------
  await page.getByRole('link', { name: /Locations/ }).click();
  await page.getByRole('button', { name: 'Add location' }).click();
  await page.getByRole('dialog').getByLabel('Name').fill('Hill Paddock');
  await page.getByRole('dialog').getByLabel('Type').selectOption('paddock');
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click();
  await page.reload();
  await expect(page.getByText('Hill Paddock')).toBeVisible();

  // --- Export -------------------------------------------------------------------------------------
  await page.goto('/livestock');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: /Excel/ }).click();
  expect((await download).suggestedFilename()).toMatch(/^livestock-register-.*\.xlsx$/);
});
