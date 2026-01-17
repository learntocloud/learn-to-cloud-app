import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// Set VITE_API_URL to empty string for tests to use relative URLs consistently
// This matches the CI environment and production behavior (where frontend proxies to backend)
vi.stubEnv('VITE_API_URL', '');

// Cleanup after each test
afterEach(() => {
  cleanup();
});
