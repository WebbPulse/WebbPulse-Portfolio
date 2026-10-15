import React from 'react';
import { PublicShell, HOME_NAV } from '../components/layout';
import {
  Hero,
  Skills,
  Projects,
  Experience,
  Blog,
  Contact,
} from '../components/sections';
import { useDocumentMeta } from '../hooks';

/** The public home page: the system map, then the rest section by section. */
const Home: React.FC = () => {
  useDocumentMeta({});
  return (
    <PublicShell navigationItems={HOME_NAV}>
      <main id="main" className="flex-1" data-testid="page-home">
        <Hero />
        <Projects />
        <Experience />
        <Skills />
        <Blog />
        <Contact />
      </main>
    </PublicShell>
  );
};

export default Home;
