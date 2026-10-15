import { useCallback, useSyncExternalStore } from 'react';

/** The two drawing themes: paper and ink, or blueprint. */
export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'cp-theme';

const listeners = new Set<() => void>();

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

/** The theme the prerender and the hydrating render draw with. */
const serverTheme = (): Theme => 'light';

/** Puts a theme on the document and tells every subscriber. */
function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme);
  listeners.forEach((listener) => listener());
}

/** Follows theme changes, including OS changes while no choice is saved. */
function subscribe(onChange: () => void): () => void {
  listeners.add(onChange);
  const mq = window.matchMedia
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null;
  const onSystem = (e: MediaQueryListEvent) => {
    if (readSaved() === null) applyTheme(e.matches ? 'dark' : 'light');
  };
  mq?.addEventListener('change', onSystem);
  return () => {
    listeners.delete(onChange);
    mq?.removeEventListener('change', onSystem);
  };
}

/**
 * The active theme and a toggle that saves the choice.
 *
 * Follows the OS preference until the visitor picks a theme, then keeps that
 * choice in localStorage when storage is available. Reads light while
 * hydrating, so markup that depends on it matches the prerendered HTML.
 */
export function useTheme(): { theme: Theme; toggleTheme: () => void } {
  const theme = useSyncExternalStore(subscribe, currentTheme, serverTheme);

  const toggleTheme = useCallback(() => {
    const next: Theme = currentTheme() === 'dark' ? 'light' : 'dark';
    save(next);
    applyTheme(next);
  }, []);

  return { theme, toggleTheme };
}
