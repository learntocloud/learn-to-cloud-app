import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  getSystemTheme,
  getThemePreference,
  applyTheme,
  setThemePreference,
  initTheme,
  onThemeChange,
} from './theme';

describe('theme utilities', () => {
  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear();
    // Clear document classes
    document.documentElement.className = '';
    delete document.documentElement.dataset.theme;
  });

  describe('getSystemTheme', () => {
    it('returns "dark" when system prefers dark mode', () => {
      // Mock matchMedia to return dark preference
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: vi.fn().mockImplementation((query: string) => ({
          matches: query === '(prefers-color-scheme: dark)',
          media: query,
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        })),
      });

      expect(getSystemTheme()).toBe('dark');
    });

    it('returns "light" when system prefers light mode', () => {
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: vi.fn().mockImplementation((query: string) => ({
          matches: false,
          media: query,
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        })),
      });

      expect(getSystemTheme()).toBe('light');
    });
  });

  describe('getThemePreference', () => {
    it('returns stored preference if available', () => {
      localStorage.setItem('ltc.theme', 'dark');
      expect(getThemePreference()).toBe('dark');
    });

    it('falls back to system theme when no stored preference', () => {
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: vi.fn().mockImplementation(() => ({
          matches: true,
          media: '',
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        })),
      });

      expect(getThemePreference()).toBe('dark');
    });

    it('ignores invalid stored values', () => {
      localStorage.setItem('ltc.theme', 'invalid');
      expect(getThemePreference()).toBe('light');
    });
  });

  describe('applyTheme', () => {
    it('adds "dark" class when preference is dark', () => {
      applyTheme('dark');
      expect(document.documentElement.classList.contains('dark')).toBe(true);
      expect(document.documentElement.dataset.theme).toBe('dark');
    });

    it('removes "dark" class when preference is light', () => {
      document.documentElement.classList.add('dark');
      applyTheme('light');
      expect(document.documentElement.classList.contains('dark')).toBe(false);
      expect(document.documentElement.dataset.theme).toBe('light');
    });

    it('emits theme change event', () => {
      const handler = vi.fn();
      window.addEventListener('ltc:theme-change', handler);

      applyTheme('dark');

      expect(handler).toHaveBeenCalledWith(
        expect.objectContaining({
          detail: { preference: 'dark' },
        })
      );

      window.removeEventListener('ltc:theme-change', handler);
    });
  });

  describe('setThemePreference', () => {
    it('stores preference and applies theme', () => {
      setThemePreference('dark');

      expect(localStorage.getItem('ltc.theme')).toBe('dark');
      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });
  });

  describe('initTheme', () => {
    it('initializes theme from storage', () => {
      localStorage.setItem('ltc.theme', 'dark');
      initTheme();

      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });

    it('initializes theme from system when no storage', () => {
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: vi.fn().mockImplementation(() => ({
          matches: true,
          media: '',
          onchange: null,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        })),
      });

      initTheme();

      expect(localStorage.getItem('ltc.theme')).toBe('dark');
      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });
  });

  describe('onThemeChange', () => {
    it('calls handler when theme changes', () => {
      const handler = vi.fn();
      const unsubscribe = onThemeChange(handler);

      applyTheme('dark');

      expect(handler).toHaveBeenCalledWith('dark');

      unsubscribe();
    });

    it('stops calling handler after unsubscribe', () => {
      const handler = vi.fn();
      const unsubscribe = onThemeChange(handler);

      applyTheme('dark');
      expect(handler).toHaveBeenCalledTimes(1);

      unsubscribe();
      applyTheme('light');
      expect(handler).toHaveBeenCalledTimes(1); // Should not increase
    });
  });
});
