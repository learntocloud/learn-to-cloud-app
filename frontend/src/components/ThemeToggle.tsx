import { useEffect, useMemo, useState } from 'react';
import {
  getThemePreference,
  onThemeChange,
  setThemePreference,
  type ThemePreference,
} from '@/lib/theme';

function nextPreference(current: ThemePreference): ThemePreference {
  return current === 'dark' ? 'light' : 'dark';
}

function Icon({ preference }: { preference: ThemePreference }) {
  if (preference === 'dark') {
    return (
      <svg
        className="h-5 w-5"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        aria-hidden="true"
      >
        <path d="M21 12.8A8.5 8.5 0 0 1 11.2 3a7 7 0 1 0 9.8 9.8Z" />
      </svg>
    );
  }

  return (
    <svg
      className="h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2" />
      <path d="M12 20v2" />
      <path d="M4.93 4.93l1.41 1.41" />
      <path d="M17.66 17.66l1.41 1.41" />
      <path d="M2 12h2" />
      <path d="M20 12h2" />
      <path d="M4.93 19.07l1.41-1.41" />
      <path d="M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

export function ThemeToggle() {
  const [preference, setPreference] = useState<ThemePreference>(() => getThemePreference());

  useEffect(() => {
    const unsubscribe = onThemeChange((p) => setPreference(p));
    return unsubscribe;
  }, []);

  const title = useMemo(() => (preference === 'dark' ? 'Theme: Dark' : 'Theme: Light'), [preference]);

  return (
    <button
      type="button"
      onClick={() => setThemePreference(nextPreference(preference))}
      className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200 dark:hover:bg-gray-800 transition-colors"
      aria-label={title}
      title={title}
    >
      <Icon preference={preference} />
    </button>
  );
}
