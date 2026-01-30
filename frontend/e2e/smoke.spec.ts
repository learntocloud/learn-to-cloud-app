/**
 * Smoke tests for public routes.
 * These tests don't require authentication.
 */

import { test, expect } from '@playwright/test';

test.describe('Public Routes', () => {
  test('homepage loads successfully', async ({ page }) => {
    await page.goto('/');

    // Verify the app renders
    await expect(page).toHaveTitle(/learn to cloud/i);
    await expect(page.getByRole('navigation')).toBeVisible();
  });

  test('phases page shows all phases', async ({ page }) => {
    await page.goto('/phases');

    // Wait for page to load (shows "Your Cloud Engineering Journey")
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/phase 0/i).first()).toBeVisible();
  });

  test('phase detail page loads public view', async ({ page }) => {
    await page.goto('/phase1');

    // Verify phase content renders
    await expect(page.getByRole('main')).toBeVisible();
    // Public view should show sign-in CTA or limited content
  });

  test('FAQ page loads', async ({ page }) => {
    await page.goto('/faq');

    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });

  test('404 page shows for invalid routes', async ({ page }) => {
    await page.goto('/this-route-does-not-exist');

    // NotFoundPage shows "404" as heading and "doesn't exist" text
    await expect(page.getByRole('heading', { name: '404' })).toBeVisible();
  });

  test('navigation links work', async ({ page }) => {
    await page.goto('/');

    // Click phases link in nav
    await page.getByRole('link', { name: /phases/i }).first().click();
    await expect(page).toHaveURL(/phases/);
  });
});
