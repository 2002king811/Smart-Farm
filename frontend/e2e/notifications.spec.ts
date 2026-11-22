import { expect, test } from '@playwright/test';

import { signUpFarm } from './helpers';

test('notifications: test message, bell badge, delivery status and settings', async ({ page }) => {
  await signUpFarm(page, 'Bell Farm');

  await page.goto('/settings/notifications');
  await expect(page.getByRole('heading', { name: 'What you get, and where' })).toBeVisible();

  // In-app test: appears under the bell straight away.
  await page.getByRole('button', { name: 'Send test message' }).click();
  await expect(
    page.getByRole('status').filter({ hasText: 'Sent to your notifications in the app.' }),
  ).toBeVisible();
  await expect(page.getByTestId('bell-count')).toHaveText('1');

  // SMS test before the phone is confirmed: reported as not sent, never as success.
  await page.getByLabel('Channel').selectOption('sms');
  await page.getByRole('button', { name: 'Send test message' }).click();
  await expect(page.getByText('Not sent: Mobile number not confirmed.')).toBeVisible();

  // Switch overdue SMS off and move quiet hours.
  const sms = page.getByRole('checkbox', { name: 'Overdue activity: SMS' });
  await sms.uncheck();
  await page.getByLabel('Quiet from').fill('22:00');
  await page.getByRole('button', { name: 'Save notification settings' }).click();
  await expect(page.getByText('Notification settings saved.')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('checkbox', { name: 'Overdue activity: SMS' })).not.toBeChecked();
  await expect(page.getByLabel('Quiet from')).toHaveValue('22:00');

  // The Notifications page shows both, with the SMS delivery marked Failed.
  await page.getByRole('link', { name: /Notifications: 2 unread/ }).click();
  await expect(page.getByRole('heading', { level: 2, name: 'Notifications' })).toBeVisible();
  const delivery = page.getByRole('list', { name: 'Delivery' });
  await expect(delivery.getByText('Failed')).toBeVisible();
  await expect(delivery.getByText('Mobile number not confirmed')).toBeVisible();
  await page.getByRole('button', { name: 'Mark all as read' }).click();
  await expect(page.getByText('All notifications marked as read.')).toBeVisible();
  await expect(page.getByTestId('bell-count')).toHaveCount(0);
});
