import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import type { NavigationItem } from '../../types';

interface HeaderProps {
  navigationItems?: NavigationItem[];
}

/** The sticky site header, with in-page navigation. */
const Header: React.FC<HeaderProps> = ({ navigationItems = [] }) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const renderNavigationItem = (item: NavigationItem, isMobile = false) => {
    const baseClasses = isMobile
      ? 'block px-3 py-2 rounded-md text-base font-medium text-surface-300 hover:text-surface-50 transition-colors'
      : 'text-sm font-medium text-surface-300 hover:text-surface-50 transition-colors';

    const isInternalRoute =
      item.href.startsWith('/') && !item.href.includes('#');

    if (isInternalRoute) {
      return (
        <Link
          key={item.href}
          to={item.href}
          className={baseClasses}
          onClick={() => isMobile && setIsMobileMenuOpen(false)}
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
        onClick={() => isMobile && setIsMobileMenuOpen(false)}
      >
        {item.label}
      </a>
    );
  };

  return (
    <header
      className={`sticky top-0 z-50 transition-all duration-300 ${
        scrolled
          ? 'bg-surface-950/80 backdrop-blur-xl border-b border-surface-800/60'
          : 'bg-transparent border-b border-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        <div className="flex justify-between items-center h-16">
          <Link
            to="/"
            className="font-display text-lg font-bold text-surface-50 hover:opacity-80 transition-opacity"
          >
            Tyler <span className="text-gradient">Webb</span>
          </Link>

          <nav className="hidden md:flex items-center gap-7">
            {navigationItems.map((item) => renderNavigationItem(item))}
            {import.meta.env.DEV && (
              <Link
                to="/admin"
                className="text-sm font-medium text-accent-cyan-400 hover:text-accent-cyan-300 transition-colors"
              >
                Admin
              </Link>
            )}
          </nav>

          <button
            type="button"
            onClick={() => setIsMobileMenuOpen((prev) => !prev)}
            aria-label={isMobileMenuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={isMobileMenuOpen}
            className="md:hidden text-surface-200 hover:text-surface-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-cyan-400 rounded-md p-1"
          >
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden="true"
            >
              {isMobileMenuOpen ? (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 18L18 6M6 6l12 12"
                />
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 6h16M4 12h16M4 18h16"
                />
              )}
            </svg>
          </button>
        </div>

        {isMobileMenuOpen && (
          <div className="md:hidden pb-4">
            <div className="space-y-1 pt-2 border-t border-surface-800/60">
              {navigationItems.map((item) => renderNavigationItem(item, true))}
              {import.meta.env.DEV && (
                <Link
                  to="/admin"
                  className="block px-3 py-2 rounded-md text-base font-medium text-accent-cyan-400"
                  onClick={() => setIsMobileMenuOpen(false)}
                >
                  Admin
                </Link>
              )}
            </div>
          </div>
        )}
      </div>
    </header>
  );
};

export default Header;
