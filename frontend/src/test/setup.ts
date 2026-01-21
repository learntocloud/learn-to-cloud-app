/**
 * Vitest global test setup.
 * Configures testing environment, DOM matchers, and cleanup.
 */

import { expect, afterEach, beforeAll, afterAll } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as matchers from '@testing-library/jest-dom/matchers';
import { server } from '../mocks/server';

// Extend Vitest's expect with DOM matchers (toBeInTheDocument, toHaveTextContent, etc.)
expect.extend(matchers);

// MSW Server setup
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});

afterEach(() => {
  // Reset MSW handlers to defaults after each test
  server.resetHandlers();
  // Cleanup DOM after each test
  cleanup();
});

afterAll(() => {
  server.close();
});

// Mock window.matchMedia for components that use it (e.g., theme detection)
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Mock localStorage for theme persistence tests
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// Reset localStorage before each test
afterEach(() => {
  localStorageMock.clear();
});
