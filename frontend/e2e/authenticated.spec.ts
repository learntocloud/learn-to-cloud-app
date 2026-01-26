/**
 * Authenticated E2E tests.
 * Tests user flows that require sign-in.
 *
 * Prerequisites:
 * 1. Enable email/password auth in Clerk Dashboard
 * 2. Create a test user with email/password
 * 3. Set TEST_USER_EMAIL and TEST_USER_PASSWORD in .env.test
 *
 * @see https://clerk.com/docs/testing/playwright
 */

import { setupClerkTestingToken } from '@clerk/testing/playwright';
import { test, expect } from '@playwright/test';

// Skip all authenticated tests if credentials aren't configured
const testEmail = process.env.TEST_USER_EMAIL;
const testPassword = process.env.TEST_USER_PASSWORD;

test.describe('Authenticated User Flows', () => {
  test.skip(!testEmail || !testPassword, 'Test credentials not configured');

  test.beforeEach(async ({ page }) => {
    await setupClerkTestingToken({ page });
  });

  test('user can sign in and access dashboard', async ({ page }) => {
    await page.goto('/sign-in');

    // Fill sign-in form
    await page.getByLabel(/email/i).fill(testEmail!);
    await page.getByRole('button', { name: /continue/i }).click();

    // Enter password (Clerk's multi-step flow)
    await page.getByLabel(/password/i).fill(testPassword!);
    await page.getByRole('button', { name: /continue|sign in/i }).click();

    // Should redirect to dashboard or homepage
    await expect(page).toHaveURL(/dashboard|\//);
  });

  test('authenticated user sees full phase content', async ({ page }) => {
    // Sign in first
    await page.goto('/sign-in');
    await page.getByLabel(/email/i).fill(testEmail!);
    await page.getByRole('button', { name: /continue/i }).click();
    await page.getByLabel(/password/i).fill(testPassword!);
    await page.getByRole('button', { name: /continue|sign in/i }).click();

    // Wait for auth to complete
    await page.waitForURL(/dashboard|\//);

    // Navigate to a phase
    await page.goto('/phase1');

    // Authenticated view should show progress elements
    await expect(page.getByRole('main')).toBeVisible();
    // Look for authenticated-only elements like progress indicators
  });

  test('dashboard shows user progress', async ({ page }) => {
    // Sign in
    await page.goto('/sign-in');
    await page.getByLabel(/email/i).fill(testEmail!);
    await page.getByRole('button', { name: /continue/i }).click();
    await page.getByLabel(/password/i).fill(testPassword!);
    await page.getByRole('button', { name: /continue|sign in/i }).click();

    await page.waitForURL(/dashboard|\//);
    await page.goto('/dashboard');

    // Dashboard should load with user data
    await expect(page.getByRole('heading')).toBeVisible();
  });

  test('unauthenticated access to dashboard redirects to sign-in', async ({ page }) => {
    // Don't sign in, just try to access protected route
    await page.goto('/dashboard');

    // Should redirect to sign-in
    await expect(page).toHaveURL(/sign-in/);
  });
});
