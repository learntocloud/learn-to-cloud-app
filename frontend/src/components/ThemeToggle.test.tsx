/**
 * Unit tests for components/ThemeToggle.tsx
 *
 * Tests the ThemeToggle component to ensure it properly toggles between
 * light and dark themes and persists preferences.
 *
 * Total test cases: 7
 * - TestThemeToggle: 7 tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeToggle } from './ThemeToggle';
import { getThemePreference, setThemePreference } from '@/lib/theme';
import { setupLocalStorageMock } from '../test/test-utils';

describe('TestThemeToggle', () => {
  beforeEach(() => {
    setupLocalStorageMock();
    localStorage.clear();
    // Reset theme preference
    setThemePreference('light');
  });

  it('should render theme toggle button', () => {
    render(<ThemeToggle />);

    const button = screen.getByRole('button', { name: /theme:/i });
    expect(button).toBeInTheDocument();
  });

  it('should show light theme icon when theme is light', () => {
    setThemePreference('light');
    render(<ThemeToggle />);

    const button = screen.getByRole('button', { name: /theme: light/i });
    expect(button).toBeInTheDocument();
  });

  it('should show dark theme icon when theme is dark', () => {
    setThemePreference('dark');
    render(<ThemeToggle />);

    const button = screen.getByRole('button', { name: /theme: dark/i });
    expect(button).toBeInTheDocument();
  });

  it('should toggle from light to dark when clicked', async () => {
    const user = userEvent.setup();
    setThemePreference('light');

    render(<ThemeToggle />);

    const button = screen.getByRole('button', { name: /theme: light/i });
    await user.click(button);

    await waitFor(() => {
      expect(getThemePreference()).toBe('dark');
    });
  });

  it('should toggle from dark to light when clicked', async () => {
    const user = userEvent.setup();
    setThemePreference('dark');

    render(<ThemeToggle />);

    const button = screen.getByRole('button', { name: /theme: dark/i });
    await user.click(button);

    await waitFor(() => {
      expect(getThemePreference()).toBe('light');
    });
  });

  it('should update button label after theme change', async () => {
    const user = userEvent.setup();
    setThemePreference('light');

    render(<ThemeToggle />);

    const button = screen.getByRole('button', { name: /theme: light/i });
    await user.click(button);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /theme: dark/i })).toBeInTheDocument();
    });
  });

  it('should sync theme changes from other components', async () => {
    setThemePreference('light');
    render(<ThemeToggle />);

    expect(screen.getByRole('button', { name: /theme: light/i })).toBeInTheDocument();

    // Simulate theme change from another component
    setThemePreference('dark');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /theme: dark/i })).toBeInTheDocument();
    });
  });
});
