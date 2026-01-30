/**
 * Global setup for Playwright E2E tests.
 * Initializes Clerk testing tokens for authenticated test flows.
 *
 * @see https://clerk.com/docs/testing/playwright
 */

import { clerkSetup } from '@clerk/testing/playwright';
import { test as setup } from '@playwright/test';
import * as dotenv from 'dotenv';
import { fileURLToPath } from 'url';
import * as path from 'path';

// ES module workaround for __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load test environment variables
dotenv.config({ path: path.resolve(__dirname, '../.env.test') });

// Setup must run serially when Playwright is configured for parallel execution
setup.describe.configure({ mode: 'serial' });

setup('initialize Clerk testing', async () => {
  // Only initialize Clerk if secret key is available (for authenticated tests)
  if (process.env.CLERK_SECRET_KEY) {
    await clerkSetup();
  }
});
