import React from 'react';
import { Header, Footer } from '../components/layout';
import {
  Hero,
  About,
  Skills,
  Projects,
  Experience,
  Blog,
  Contact,
} from '../components/sections';
import type { NavigationItem } from '../types';

/** The public single page site, section by section. */
const Home: React.FC = () => {
  const navigationItems: NavigationItem[] = [
    { label: 'About', href: '#about' },
    { label: 'Skills', href: '#skills' },
    { label: 'Projects', href: '#projects' },
    { label: 'Experience', href: '#experience' },
    { label: 'Blog', href: '#blog' },
    { label: 'Contact', href: '#contact' },
  ];

  return (
    <div className="min-h-screen">
      <Header navigationItems={navigationItems} />
      <main>
        <Hero />
        <About />
        <Skills />
        <Projects />
        <Experience />
        <Blog />
        <Contact />
      </main>
      <Footer />
    </div>
  );
};

export default Home;
