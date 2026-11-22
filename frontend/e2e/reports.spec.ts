import { expect, test } from '@playwright/test';

import { signUpFarm } from './helpers';

test('dashboard and reports: figures, preview and PDF/Excel export', async ({ page }) => {
  await signUpFarm(page, 'Report Farm');

  // Register one animal so the figures are not all zero.
  await page.goto('/livestock/new');
  await expect(page.getByLabel('Animal ID *')).toHaveValue(/-001$/);
  await page.getByLabel('Name', { exact: true }).fill('Neema');
  await page.getByLabel('Female', { exact: true }).check();
  await page.getByLabel('Date of birth *').fill('2024-03-15');
  await page.getByRole('button', { name: 'Register animal' }).click();
  await expect(page.getByRole('heading', { name: /-001 · Neema/ })).toBeVisible();

  await page.goto('/dashboard');
  const total = page.getByRole('region', { name: 'Total animals' });
  await expect(total).toContainText('1');
  await expect(page.getByRole('heading', { name: 'Trends' })).toBeVisible();

  await page.getByRole('link', { name: 'Reports', exact: true }).first().click();
  await page.getByRole('link', { name: /Livestock Register/ }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'Livestock Register' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Neema' })).toBeVisible();

  const pdf = page.waitForEvent('download');
  await page.getByRole('button', { name: 'PDF' }).click();
  expect((await pdf).suggestedFilename()).toMatch(/^livestock_register_\d{8}-\d{8}\.pdf$/);

  await page.goto('/reports/vaccination');
  await expect(page.getByRole('heading', { level: 2, name: 'Vaccination Report' })).toBeVisible();
  const xlsx = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Excel' }).click();
  expect((await xlsx).suggestedFilename()).toMatch(/^vaccination_.*\.xlsx$/);
});
