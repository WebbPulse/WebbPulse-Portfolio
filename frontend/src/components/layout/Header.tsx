import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { NavigationItem } from '../../types';
import { useClientValue, useTheme } from '../../hooks';
import { CommandMenu } from './CommandMenu';
import { SITE_NAV } from './nav';

interface HeaderProps {
  navigationItems?: NavigationItem[];
}

/** True on Apple platforms, where the menu shortcut reads as the Command key. */
function isApplePlatform(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
}

/** The registration mark used as the site mark beside the name. */
const SiteMark: React.FC = () => (
  <svg
    className="h-5 w-5 text-accent"
    viewBox="0 0 20 20"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.25"
    aria-hidden="true"
  >
    <circle cx="10" cy="10" r="5.5" />
    <path d="M10 1v18M1 10h18" />
  </svg>
);

/**
 * The sun and moon glyphs for the theme switch. Both are drawn and the
 * document theme picks one, so the prerendered button never shows the wrong
 * glyph before hydration.
 */
const ThemeGlyph: React.FC = () => (
  <>
    <svg
      className="hidden h-4 w-4 [[data-theme=dark]_&]:block"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.25"
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6 13 13M3 13l1.4-1.4M11.6 4.4 13 3" />
    </svg>
    <svg
      className="h-4 w-4 [[data-theme=dark]_&]:hidden"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.25"
      aria-hidden="true"
    >
      <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7Z" />
    </svg>
  </>
);

/**
 * The sticky site header: name and role, section navigation, the theme switch
 * and the command menu button (also bound to Cmd+K or Ctrl+K).
 */
const Header: React.FC<HeaderProps> = ({ navigationItems = SITE_NAV }) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const apple = useClientValue(isApplePlatform, false);

  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setMenuOpen((open) => !open);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const renderNavigationItem = (item: NavigationItem, isMobile = false) => {
    const baseClasses = isMobile
      ? 'flex items-center justify-between border-b border-line px-1 py-3 text-base text-ink hover:text-accent transition-colors'
      : 'px-2.5 py-1.5 text-sm text-ink-muted hover:text-ink transition-colors';

    const isInternalRoute =
      item.href.startsWith('/') && !item.href.includes('#');
    const close = () => isMobile && setIsMobileMenuOpen(false);

    if (isInternalRoute) {
      return (
        <Link
          key={item.href}
          to={item.href}
          className={baseClasses}
          onClick={close}
        >
          {item.label}
        </Link>
      );
    }

    return (
      <a
        key={item.href}
        href={item.href}
        className={baseClasses}
        target={item.external ? '_blank' : undefined}
        rel={item.external ? 'noopener noreferrer' : undefined}
        onClick={close}
      >
        {item.label}
      </a>
    );
  };

  const nextTheme = theme === 'dark' ? 'light' : 'dark';

  return (
    <header className="sticky top-0 z-50 border-b border-line bg-paper/90 backdrop-blur-sm">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-[70] focus:border focus:border-line-strong focus:bg-paper-raised focus:px-3 focus:py-2 focus:text-sm focus:text-ink"
      >
        Skip to content
      </a>
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-4 px-4 sm:px-8">
        <Link
          to="/"
          className="group flex min-w-0 items-center gap-2.5"
          aria-label="Tyler Webb, software engineer, home"
        >
          <SiteMark />
          <span className="truncate text-[0.95rem] font-semibold tracking-tight text-ink">
            Tyler Webb
          </span>
          <span
            className="hidden h-4 w-px bg-line-strong sm:block"
            aria-hidden="true"
          />
          <span className="mono-label hidden sm:block">Software engineer</span>
        </Link>

        <nav
          aria-label="Primary"
          className="ml-auto hidden items-center lg:flex"
        >
          {navigationItems.map((item) => renderNavigationItem(item))}
        </nav>

        <div className="ml-auto flex items-center gap-2 lg:ml-2">
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            aria-haspopup="dialog"
            aria-label="Open command menu"
            className="flex h-8 items-center gap-2 border border-line px-2 text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
          >
            <svg
              className="h-3.5 w-3.5"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
            >
              <circle cx="7" cy="7" r="4.5" />
              <path d="m10.5 10.5 3.5 3.5" />
            </svg>
            <kbd className="hidden font-mono text-xs tracking-wide sm:inline">
              {apple ? '⌘K' : 'Ctrl K'}
            </kbd>
          </button>

          <button
            type="button"
            onClick={toggleTheme}
            aria-label={`Switch to ${nextTheme} theme`}
            title={`Switch to ${nextTheme} theme`}
            className="flex h-8 w-8 items-center justify-center border border-line text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
          >
            <ThemeGlyph />
          </button>

          <button
            type="button"
            onClick={() => setIsMobileMenuOpen((prev) => !prev)}
            aria-label={isMobileMenuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={isMobileMenuOpen}
            aria-controls="mobile-nav"
            className="flex h-8 w-8 items-center justify-center border border-line text-ink-muted transition-colors hover:text-ink lg:hidden"
          >
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 16 16"
              stroke="currentColor"
              strokeWidth={1.5}
              aria-hidden="true"
            >
              {isMobileMenuOpen ? (
                <path d="M3.5 3.5l9 9M12.5 3.5l-9 9" />
              ) : (
                <path d="M2 4.5h12M2 8h12M2 11.5h12" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {isMobileMenuOpen && (
        <nav
          id="mobile-nav"
          aria-label="Primary"
          className="border-t border-line bg-paper lg:hidden"
        >
          <div className="mx-auto flex max-w-6xl flex-col px-4 pb-4 sm:px-8">
            {navigationItems.map((item) => renderNavigationItem(item, true))}
          </div>
        </nav>
      )}

      <CommandMenu
        open={menuOpen}
        onClose={closeMenu}
        items={navigationItems}
        onToggleTheme={toggleTheme}
      />
    </header>
  );
};

export default Header;
