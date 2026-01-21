/**
 * Tests for ThemeToggle component.
 * Tests theme switching behavior and accessibility.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, userEvent } from '../test/test-utils';
import { ThemeToggle } from './ThemeToggle';

describe('ThemeToggle', () => {
  beforeEach(() => {
    // Reset document classes before each test
    document.documentElement.classList.remove('dark');
    document.documentElement.dataset.theme = 'light';
    localStorage.clear();
  });

  it('renders theme toggle button', () => {
    render(<ThemeToggle />);

    const button = screen.getByRole('button', { name: /theme/i });
    expect(button).toBeInTheDocument();
  });

  it('displays light theme icon when in dark mode', () => {
    localStorage.setItem('ltc.theme', 'dark');
    render(<ThemeToggle />);

    const button = screen.getByRole('button');
    // In dark mode, button should show sun icon (to switch to light)
    expect(button).toHaveAttribute('aria-label', 'Theme: Dark');
  });

  it('displays dark theme icon when in light mode', () => {
    localStorage.setItem('ltc.theme', 'light');
    render(<ThemeToggle />);

    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-label', 'Theme: Light');
  });

  it('toggles theme on click', async () => {
    const user = userEvent.setup();
    localStorage.setItem('ltc.theme', 'light');
    render(<ThemeToggle />);

    const button = screen.getByRole('button');

    // Initially light
    expect(button).toHaveAttribute('aria-label', 'Theme: Light');

    // Click to switch to dark
    await user.click(button);

    expect(localStorage.getItem('ltc.theme')).toBe('dark');
  });

  it('toggles from dark to light', async () => {
    const user = userEvent.setup();
    localStorage.setItem('ltc.theme', 'dark');
    render(<ThemeToggle />);

    const button = screen.getByRole('button');
    await user.click(button);

    expect(localStorage.getItem('ltc.theme')).toBe('light');
  });

  it('has accessible button with title', () => {
    render(<ThemeToggle />);

    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('title');
    expect(button).toHaveAttribute('aria-label');
  });

  it('uses system theme when no preference is stored', () => {
    localStorage.clear();

    // Mock system preferring dark mode
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: query === '(prefers-color-scheme: dark)',
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });

    render(<ThemeToggle />);

    const button = screen.getByRole('button');
    expect(button).toHaveAttribute('aria-label', 'Theme: Dark');
  });
});
