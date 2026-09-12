import React from 'react';
import { Link } from 'react-router-dom';
import { Header, Footer } from '../components/layout';
import { Button, GradientText } from '../components/common';
import type { NavigationItem } from '../types';

const NAV: NavigationItem[] = [
  { label: 'Home', href: '/' },
  { label: 'About', href: '/#about' },
  { label: 'Skills', href: '/#skills' },
  { label: 'Projects', href: '/#projects' },
  { label: 'Experience', href: '/#experience' },
  { label: 'Blog', href: '/blog' },
  { label: 'Contact', href: '/#contact' },
];

/** The catch-all page for a URL that matches no route. */
export const NotFound: React.FC = () => (
  <div className="min-h-screen">
    <Header navigationItems={NAV} />
    <main className="relative py-20 sm:py-28 overflow-hidden">
      <div className="absolute inset-0 bg-mesh-1 opacity-40 pointer-events-none" />

      <div className="relative z-10 max-w-3xl mx-auto px-6 sm:px-8 text-center">
        <p className="font-display text-sm uppercase tracking-[0.2em] text-surface-400 mb-4">
          Error 404
        </p>
        <h1 className="font-display text-4xl sm:text-5xl font-bold text-surface-50 mb-6">
          <GradientText as="span">Page not found</GradientText>
        </h1>
        <p className="text-surface-300 leading-relaxed mb-10">
          The page you asked for does not exist, or it has moved somewhere else
          on this site.
        </p>
        <Link to="/">
          <Button variant="primary" size="lg">
            Back to home
          </Button>
        </Link>
      </div>
    </main>
    <Footer />
  </div>
);

export default NotFound;
