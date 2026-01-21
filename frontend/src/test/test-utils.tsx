/**
 * Test utilities for React component testing.
 * Provides custom render function with all required providers.
 */

import { ReactElement, ReactNode } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Create a fresh QueryClient for each test to prevent state leakage
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false, // Don't retry failed queries in tests
        gcTime: 0, // Disable garbage collection time (formerly cacheTime)
      },
      mutations: {
        retry: false,
      },
    },
  });
}

interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  /**
   * Provide a custom QueryClient for testing specific cache scenarios.
   */
  queryClient?: QueryClient;
  /**
   * Initial route for MemoryRouter (use when testing route-dependent components).
   */
  initialEntries?: string[];
  /**
   * Use BrowserRouter instead of MemoryRouter (for testing history interactions).
   */
  useBrowserRouter?: boolean;
}

/**
 * Mock Clerk hooks for testing authenticated components.
 * Import this object and modify values in individual tests.
 */
export const mockClerkUser = {
  isSignedIn: false,
  isLoaded: true,
  user: null as null | {
    id: string;
    firstName: string | null;
    lastName: string | null;
    imageUrl: string | null;
  },
};

/**
 * Custom render function that wraps components in all required providers.
 *
 * @example
 * // Basic usage
 * render(<MyComponent />)
 *
 * @example
 * // With initial route
 * render(<MyComponent />, { initialEntries: ['/dashboard'] })
 *
 * @example
 * // With custom QueryClient
 * const queryClient = new QueryClient();
 * render(<MyComponent />, { queryClient })
 */
function customRender(
  ui: ReactElement,
  {
    queryClient = createTestQueryClient(),
    initialEntries = ['/'],
    useBrowserRouter = false,
    ...renderOptions
  }: CustomRenderOptions = {}
) {
  function AllProviders({ children }: { children: ReactNode }) {
    const Router = useBrowserRouter ? BrowserRouter : MemoryRouter;
    const routerProps = useBrowserRouter ? {} : { initialEntries };

    return (
      <QueryClientProvider client={queryClient}>
        <Router {...routerProps}>{children}</Router>
      </QueryClientProvider>
    );
  }

  return {
    ...render(ui, { wrapper: AllProviders, ...renderOptions }),
    queryClient,
  };
}

// Re-export everything from testing-library
export * from '@testing-library/react';
export { default as userEvent } from '@testing-library/user-event';

// Export custom render as default render
export { customRender as render, createTestQueryClient };
