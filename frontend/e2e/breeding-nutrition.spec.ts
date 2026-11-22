import { expect, test, type Page } from '@playwright/test';

import { signUpFarm } from './helpers';

async function register(page: Page, name: string, sex: 'Male' | 'Female') {
  await page.goto('/livestock/new');
  await page.getByLabel('Name', { exact: true }).fill(name);
  await page.getByLabel(sex, { exact: true }).check();
  await page.getByLabel('Date of birth *').fill('2023-06-01');
  await page.getByLabel('Location', { exact: true }).selectOption({ label: 'Night Pen' });
  await page.getByRole('button', { name: 'Register animal' }).click();
  await expect(page.getByRole('heading', { name: new RegExp(name) })).toBeVisible();
}

/** Phase 5 "done when": registering a birth adds the kids to the register, and feeding lowers
 * the stock. */
test('mating, pregnancy, birth adds kids to the register', async ({ page }) => {
  await signUpFarm(page, 'YPA FARM');
  await register(page, 'Simba', 'Male');
  await register(page, 'Neema', 'Female');

  await page.goto('/breeding');
  await page.getByRole('button', { name: 'Record mating' }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('Doe *').selectOption({ label: 'YPA-002 Neema' });
  await dialog.getByLabel('Buck *').selectOption({ label: 'YPA-001 Simba' });
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText(/Mating recorded. Expected kidding/)).toBeVisible();
  await expect(page.getByRole('link', { name: 'YPA-002 Neema' })).toBeVisible();

  await page.getByRole('link', { name: 'Matings' }).click();
  await page.getByRole('button', { name: 'Pregnant', exact: true }).click();
  await expect(page.getByText('Pregnancy confirmed.')).toBeVisible();
  await page.goto('/livestock?');
  await expect(page.getByRole('row', { name: /YPA-002 Neema/ }).getByText('Pregnant')).toBeVisible();

  // Register the birth: twins, one with a birth weight.
  await page.goto('/breeding');
  // The pregnancy card's button opens the form for Neema's mating, with her selected.
  await page
    .getByRole('article')
    .getByRole('button', { name: /Register birth/ })
    .click();
  dialog = page.getByRole('dialog');
  await expect(dialog.getByLabel('Dam (mother) *')).not.toHaveValue('');
  await dialog.getByRole('button', { name: /Add another kid/ }).click();
  const sexes = dialog.getByLabel('Sex *');
  await sexes.nth(0).selectOption('female');
  await sexes.nth(1).selectOption('male');
  await dialog.getByLabel('Name').nth(0).fill('Baraka');
  await dialog.getByLabel('Birth weight (kg)').nth(0).fill('3.4');
  await dialog.getByRole('button', { name: 'Register birth' }).click();
  await expect(page.getByText('Birth registered. YPA-003, YPA-004 added to the register.')).toBeVisible();

  // The kids are in the register, with their dam and birth weight.
  await page.goto('/livestock');
  await expect(page.getByRole('region', { name: 'Kids (under 6 months)' })).toContainText('2');
  await page.getByRole('link', { name: 'YPA-003 Baraka' }).click();
  await expect(page.getByText('3.4 kg').first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'YPA-002 Neema' })).toBeVisible();
  await page.getByRole('tab', { name: 'Timeline' }).click();
  await expect(page.getByText('Born to YPA-002')).toBeVisible();

  // Neema is now lactating and the mating is closed as Kidded.
  await page.goto('/breeding/matings');
  await expect(page.getByText('Kidded')).toBeVisible();
  await page.goto('/breeding/kids');
  await expect(page.getByRole('link', { name: 'YPA-003 Baraka' })).toBeVisible();
});

test('feeding lowers the feed stock', async ({ page }) => {
  await signUpFarm(page, 'YPA FARM');
  await page.goto('/nutrition/stock');
  await page.getByRole('button', { name: 'Update stock of Rhodes grass hay' }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('Quantity (bale)').fill('20');
  await dialog.getByLabel('Price per bale (UGX)').fill('450');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('Rhodes grass hay: 20 bale in stock.')).toBeVisible();
  const hayRow = page.getByRole('row', { name: /Rhodes grass hay/ });
  await expect(hayRow).toContainText('20 bale');

  await page.getByRole('link', { name: 'Feeding', exact: true }).click();
  await page.getByRole('button', { name: 'Record feeding' }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Feed *').selectOption({ label: 'Rhodes grass hay (20 bale in stock)' });
  await dialog.getByLabel('Quantity given *').fill('3');
  await dialog.getByLabel('Group').selectOption({ label: 'Breeding Does' });
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByText('The feeding was recorded.')).toBeVisible();

  await page.getByRole('link', { name: 'Feed stock' }).click();
  await expect(page.getByRole('row', { name: /Rhodes grass hay/ })).toContainText('17 bale');
  await page.reload();
  await expect(page.getByRole('row', { name: /Rhodes grass hay/ })).toContainText('17 bale');

  // More than is in store is refused, with the reason under the field.
  await page.getByRole('link', { name: 'Feeding', exact: true }).click();
  await page.getByRole('button', { name: 'Record feeding' }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Feed *').selectOption({ label: 'Rhodes grass hay (17 bale in stock)' });
  await dialog.getByLabel('Quantity given *').fill('50');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(dialog.getByText('Only 17 bale of Rhodes grass hay in stock.')).toBeVisible();
  await dialog.getByRole('button', { name: 'Cancel' }).click();

  await page.getByRole('link', { name: 'Stock history' }).click();
  await expect(page.getByText('-3 bale')).toBeVisible();
  await expect(page.getByText('+20 bale')).toBeVisible();
});
