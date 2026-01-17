export type ThemePreference = 'light' | 'dark';

const STORAGE_KEY = 'ltc.theme';
const THEME_CHANGE_EVENT = 'ltc:theme-change';

function safeGetStoredPreference(): ThemePreference | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === 'light' || value === 'dark') return value;
    return null;
  } catch {
    return null;
  }
}

function safeSetStoredPreference(preference: ThemePreference) {
  try {
    localStorage.setItem(STORAGE_KEY, preference);
  } catch {
    // Ignore storage access issues
  }
}

export function getSystemTheme(): EffectiveTheme {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function getThemePreference(): ThemePreference {
  return safeGetStoredPreference() ?? getSystemTheme();
}

function emitThemeChange(preference: ThemePreference) {
  window.dispatchEvent(
    new CustomEvent(THEME_CHANGE_EVENT, {
      detail: {
        preference,
      },
    })
  );
}

export function applyTheme(preference: ThemePreference) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;

  root.classList.toggle('dark', preference === 'dark');
  root.dataset.theme = preference;

  emitThemeChange(preference);
}

export function setThemePreference(preference: ThemePreference) {
  safeSetStoredPreference(preference);
  applyTheme(preference);
}

export function initTheme() {
  if (typeof window === 'undefined') return;

  const preference = getThemePreference();
  safeSetStoredPreference(preference);
  applyTheme(preference);
}

export function onThemeChange(handler: (preference: ThemePreference) => void) {
  const listener = (event: Event) => {
    const custom = event as CustomEvent<{ preference: ThemePreference }>;
    handler(custom.detail.preference);
  };

  window.addEventListener(THEME_CHANGE_EVENT, listener as EventListener);

  return () => {
    window.removeEventListener(THEME_CHANGE_EVENT, listener as EventListener);
  };
}

export type EffectiveTheme = ThemePreference;
