import { useCallback, useEffect, useState } from 'react';

/** The two drawing themes: paper and ink, or blueprint. */
export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'cp-theme';

/** Reads the saved theme choice, or null when none is saved or storage is blocked. */
function readSaved(): Theme | null {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved === 'light' || saved === 'dark' ? saved : null;
  } catch {
    return null;
  }
}

/** Saves the theme choice, doing nothing when storage is blocked. */
function save(theme: Theme): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    return;
  }
}

/** The operating system preference, light when it cannot be read. */
function systemTheme(): Theme {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

/** The theme currently on the document, as set by theme-init.js. */
function currentTheme(): Theme {
  if (typeof document === 'undefined') return 'light';
  const attr = document.documentElement.getAttribute('data-theme');
  if (attr === 'light' || attr === 'dark') return attr;
  return readSaved() ?? systemTheme();
}

/**
 * The active theme and a toggle that saves the choice.
 *
 * Follows the OS preference until the visitor picks a theme, then keeps that
 * choice in localStorage when storage is available.
 */
export function useTheme(): { theme: Theme; toggleTheme: () => void } {
  const [theme, setTheme] = useState<Theme>(currentTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      if (readSaved() === null) setTheme(e.matches ? 'dark' : 'light');
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === 'dark' ? 'light' : 'dark';
      save(next);
      return next;
    });
  }, []);

  return { theme, toggleTheme };
}
