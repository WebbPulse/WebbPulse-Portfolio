import React from 'react';
import { PublicShell, HOME_NAV } from '../components/layout';
import {
  Hero,
  About,
  Skills,
  Projects,
  Experience,
  Blog,
  Contact,
} from '../components/sections';

/** The public single page site, section by section. */
const Home: React.FC = () => (
  <PublicShell navigationItems={HOME_NAV}>
    <main id="main" className="flex-1" data-testid="page-home">
      <Hero />
      <About />
      <Skills />
      <Projects />
      <Experience />
      <Blog />
      <Contact />
    </main>
  </PublicShell>
);

export default Home;
