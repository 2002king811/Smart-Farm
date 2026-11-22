import { expect, test, type Page } from '@playwright/test';

/** Phase 2 "done when": a new farmer signs up, invites a manager and an attendant, and each
 * of them sees only what their role allows. Uses the development outbox to read the links. */

const run = Date.now().toString(36);
const owner = {
  email: `owner-${run}@example.com`,
  phone: `07${run.slice(-8).replace(/\D/g, '1').padStart(8, '1')}`,
};
const PASSWORD = 'Green-Pasture-27';

async function latestLink(page: Page, to: string): Promise<string> {
  const res = await page.request.get('/api/dev/outbox');
  const { messages } = (await res.json()) as { messages: { to: string; body: string }[] };
  const message = messages.find((m) => m.to === to && m.body.includes('/invite?token='));
  expect(message, `invitation for ${to}`).toBeTruthy();
  return (
    new URL(message!.body.match(/https?:\/\/\S+/)![0]).pathname +
    new URL(message!.body.match(/https?:\/\/\S+/)![0]).search
  );
}

async function sidebarLinks(page: Page): Promise<string[]> {
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  return (await nav.getByRole('link').allTextContents()).map((t) => t.trim());
}

test('new farmer signs up, invites a manager and an attendant; each sees only their role', async ({
  browser,
}) => {
  // --- Sign up -----------------------------------------------------------------------------------
  const ownerCtx = await browser.newContext();
  const page = await ownerCtx.newPage();
  await page.goto('/signup');
  await page.getByLabel('First name').fill('Daniel');
  await page.getByLabel('Last name').fill('Mwangi');
  await page.getByLabel('Email').fill(owner.email);
  await page.getByLabel('Mobile number').fill(owner.phone);
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByLabel('Farm name').fill(`YPA FARM ${run}`);
  await page.getByLabel('County / region').selectOption('Nakuru');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeVisible();
  await expect(page.getByText(/Confirm your mobile number/)).toBeVisible();
  expect(await sidebarLinks(page)).toContain('User Management');

  // --- Invite a manager and an attendant -----------------------------------------------------------
  await page.getByRole('link', { name: 'User Management' }).click();
  for (const [first, email, role] of [
    ['Grace', `grace-${run}@example.com`, 'farm_manager'],
    ['Peter', `peter-${run}@example.com`, 'livestock_attendant'],
  ]) {
    await page.getByRole('button', { name: 'Add user' }).click();
    const dialog = page.getByRole('dialog', { name: 'Add user' });
    await dialog.getByLabel('First name').fill(first!);
    await dialog.locator('input[type=email]').fill(email!);
    await dialog.getByLabel('Role').selectOption(role!);
    await dialog.getByRole('button', { name: 'Send invitation' }).click();
    await expect(page.getByText(`Invitation sent to ${first}.`)).toBeVisible();
  }
  await expect(page.getByRole('table').getByText(`grace-${run}@example.com`)).toBeVisible();

  // --- Each accepts in their own browser --------------------------------------------------------
  async function accept(email: string) {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    await p.goto(await latestLink(page, email));
    await expect(p.getByRole('heading', { name: /Join YPA FARM/ })).toBeVisible();
    await p.getByLabel('Choose a password').fill(PASSWORD);
    await p.getByRole('button', { name: 'Accept and create account' }).click();
    await expect(p.getByText(/You have joined/)).toBeVisible();
    return p;
  }

  const manager = await accept(`grace-${run}@example.com`);
  const managerLinks = await sidebarLinks(manager);
  expect(managerLinks).toEqual(expect.arrayContaining(['Dashboard', 'Livestock', 'Reports', 'Settings']));
  expect(managerLinks).not.toContain('User Management');
  await manager.goto('/users');
  await expect(manager.getByText('Page not found')).toBeVisible();
  await manager.goto('/settings');
  await expect(manager.getByRole('link', { name: 'Farm profile' })).toHaveCount(0);
  await expect(manager.getByRole('heading', { name: 'My profile' })).toBeVisible();

  const attendant = await accept(`peter-${run}@example.com`);
  const attendantLinks = await sidebarLinks(attendant);
  expect(attendantLinks).toEqual(['Home', 'Tasks', 'Animals', 'Calendar', 'Alerts']);
  await attendant.goto('/reports');
  await expect(attendant.getByText('Page not found')).toBeVisible();

  // --- The API agrees with the UI -------------------------------------------------------------------
  const owners = await page.request.get('/api/v1/me/farms');
  expect(owners.status()).toBe(401); // the access token lives in memory, never in cookies

  // --- Admin deactivates the attendant: access ends at once ---------------------------------------
  await page.reload();
  await page.getByRole('link', { name: 'User Management' }).click();
  await page.getByRole('button', { name: `Deactivate Peter` }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Deactivate' }).click();
  await expect(page.getByText(/is now inactive/)).toBeVisible();
  // Their only farm is gone, so their sessions were revoked: a reload lands on the login page.
  await attendant.reload();
  await expect(attendant.getByRole('heading', { name: 'Log in' })).toBeVisible();
});
