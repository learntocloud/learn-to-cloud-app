/**
 * Tests for theme utilities.
 * Tests theme preference storage, system theme detection, and theme application.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  getThemePreference,
  setThemePreference,
  applyTheme,
  getSystemTheme,
  initTheme,
  onThemeChange,
} from './theme';

describe('theme utilities', () => {
  beforeEach(() => {
    // Reset DOM state
    document.documentElement.classList.remove('dark');
    delete document.documentElement.dataset.theme;
    localStorage.clear();

    // Reset matchMedia mock to default (light mode)
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
  });

  describe('getSystemTheme', () => {
    it('returns light when system prefers light', () => {
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

      expect(getSystemTheme()).toBe('light');
    });

    it('returns dark when system prefers dark', () => {
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

      expect(getSystemTheme()).toBe('dark');
    });
  });

  describe('getThemePreference', () => {
    it('returns stored preference when available', () => {
      localStorage.setItem('ltc.theme', 'dark');
      expect(getThemePreference()).toBe('dark');
    });

    it('returns system theme when no stored preference', () => {
      localStorage.clear();
      expect(getThemePreference()).toBe('light');
    });

    it('ignores invalid stored values', () => {
      localStorage.setItem('ltc.theme', 'invalid');
      expect(getThemePreference()).toBe('light');
    });
  });

  describe('setThemePreference', () => {
    it('stores preference in localStorage', () => {
      setThemePreference('dark');
      expect(localStorage.getItem('ltc.theme')).toBe('dark');
    });

    it('applies theme to document', () => {
      setThemePreference('dark');
      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });

    it('updates data-theme attribute', () => {
      setThemePreference('dark');
      expect(document.documentElement.dataset.theme).toBe('dark');
    });
  });

  describe('applyTheme', () => {
    it('adds dark class for dark theme', () => {
      applyTheme('dark');
      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });

    it('removes dark class for light theme', () => {
      document.documentElement.classList.add('dark');
      applyTheme('light');
      expect(document.documentElement.classList.contains('dark')).toBe(false);
    });

    it('sets data-theme attribute', () => {
      applyTheme('dark');
      expect(document.documentElement.dataset.theme).toBe('dark');

      applyTheme('light');
      expect(document.documentElement.dataset.theme).toBe('light');
    });
  });

  describe('initTheme', () => {
    it('applies stored preference on init', () => {
      localStorage.setItem('ltc.theme', 'dark');
      initTheme();
      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });

    it('applies system preference when no stored value', () => {
      localStorage.clear();
      initTheme();
      // System default is light in our mock
      expect(document.documentElement.classList.contains('dark')).toBe(false);
    });

    it('saves preference to localStorage', () => {
      localStorage.clear();
      initTheme();
      expect(localStorage.getItem('ltc.theme')).not.toBeNull();
    });
  });

  describe('onThemeChange', () => {
    it('calls handler when theme changes', () => {
      const handler = vi.fn();
      const unsubscribe = onThemeChange(handler);

      setThemePreference('dark');

      expect(handler).toHaveBeenCalledWith('dark');

      unsubscribe();
    });

    it('returns unsubscribe function', () => {
      const handler = vi.fn();
      const unsubscribe = onThemeChange(handler);

      unsubscribe();
      setThemePreference('dark');

      expect(handler).not.toHaveBeenCalled();
    });

    it('supports multiple handlers', () => {
      const handler1 = vi.fn();
      const handler2 = vi.fn();

      const unsub1 = onThemeChange(handler1);
      const unsub2 = onThemeChange(handler2);

      setThemePreference('dark');

      expect(handler1).toHaveBeenCalledWith('dark');
      expect(handler2).toHaveBeenCalledWith('dark');

      unsub1();
      unsub2();
    });
  });
});
