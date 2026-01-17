/**
 * Test utilities for React component testing.
 * Provides common wrappers and helpers for testing React components with
 * React Query, Clerk authentication, and React Router.
 *
 * @vitest-environment jsdom
 */

/* eslint-disable react-refresh/only-export-components */

import { ReactElement, ReactNode } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

/**
 * Creates a fresh QueryClient for each test to avoid cache pollution.
 */
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

interface AllProvidersProps {
  children: ReactNode;
  queryClient?: QueryClient;
  initialEntries?: string[];
}

/**
 * Wrapper component that provides all necessary context providers for testing.
 */
function AllProviders({ children, queryClient, initialEntries = ['/'] }: AllProvidersProps) {
  const client = queryClient || createTestQueryClient();

  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  queryClient?: QueryClient;
  initialEntries?: string[];
}

/**
 * Custom render function that wraps components with common providers.
 * Use this instead of @testing-library/react's render for component tests.
 */
export function renderWithProviders(
  ui: ReactElement,
  { queryClient, initialEntries, ...renderOptions }: CustomRenderOptions = {}
) {
  return render(ui, {
    wrapper: ({ children }) => (
      <AllProviders queryClient={queryClient} initialEntries={initialEntries}>
        {children}
      </AllProviders>
    ),
    ...renderOptions,
  });
}

/**
 * Mock localStorage for tests.
 */
export class LocalStorageMock {
  private store: Record<string, string> = {};

  getItem(key: string): string | null {
    return this.store[key] || null;
  }

  setItem(key: string, value: string): void {
    this.store[key] = value.toString();
  }

  removeItem(key: string): void {
    delete this.store[key];
  }

  clear(): void {
    this.store = {};
  }

  get length(): number {
    return Object.keys(this.store).length;
  }

  key(index: number): string | null {
    const keys = Object.keys(this.store);
    return keys[index] || null;
  }
}

/**
 * Setup localStorage mock for tests.
 */
export function setupLocalStorageMock() {
  const localStorageMock = new LocalStorageMock();
  Object.defineProperty(window, 'localStorage', {
    value: localStorageMock,
    writable: true,
  });
  return localStorageMock;
}

// Re-export everything from @testing-library/react
export * from '@testing-library/react';
