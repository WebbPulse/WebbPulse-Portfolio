import React from 'react';
import type { NavigationItem } from '../../types';
import Header from './Header';
import Footer from './Footer';
import { SITE_NAV } from './nav';

/** Props for {@link PublicShell}. */
interface PublicShellProps {
  navigationItems?: NavigationItem[];
  children: React.ReactNode;
}

/**
 * The frame every public page sits in: the drawing grid, the header and the
 * footer. The page supplies its own `main` with `id="main"` for the skip link.
 */
export const PublicShell: React.FC<PublicShellProps> = ({
  navigationItems = SITE_NAV,
  children,
}) => (
  <div className="drawing-grid flex min-h-screen flex-col text-ink">
    <Header navigationItems={navigationItems} />
    {children}
    <Footer />
  </div>
);

export default PublicShell;
