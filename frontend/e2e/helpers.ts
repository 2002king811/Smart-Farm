import { expect, type Page } from '@playwright/test';

export const PASSWORD = 'Green-Pasture-27';

/** Signs up a fresh farm (unique per run) and lands on the dashboard. */
export async function signUpFarm(page: Page, farmName: string) {
  const run = `${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
  const digits = String(Date.now()).slice(-8);
  await page.goto('/signup');
  await page.getByLabel('First name').fill('Daniel');
  await page.getByLabel('Last name').fill('Mwangi');
  await page.getByLabel('Email').fill(`owner-${run}@example.com`);
  await page.getByLabel('Mobile number').fill(`07${digits}`);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByLabel('Farm name').fill(farmName);
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible();
  return run;
}
