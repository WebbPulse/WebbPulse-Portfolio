import { Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import { NotFound } from './pages/NotFound';
import { UnderConstruction } from './pages/UnderConstruction';
import { ErrorBoundary } from './components/common';
import {
  BlogListPage,
  BlogPostPage,
  CaseStudyPage,
  PrivacyPage,
} from './routing/pages';
import './styles/globals.css';

const UNDER_CONSTRUCTION = false;

/**
 * The route table, or the holding page when the site is switched off. Shared
 * by the browser router and the build-time prerender.
 */
export function AppRoutes() {
  return (
    <ErrorBoundary>
      <Suspense fallback={null}>
        <Routes>
          {UNDER_CONSTRUCTION ? (
            <>
              <Route path="/" element={<UnderConstruction />} />
              <Route path="/blog" element={<UnderConstruction />} />
              <Route path="/blog/:slug" element={<UnderConstruction />} />
            </>
          ) : (
            <>
              <Route path="/" element={<Home />} />
              <Route path="/blog" element={<BlogListPage />} />
              <Route path="/blog/:slug" element={<BlogPostPage />} />
              <Route path="/work/:slug" element={<CaseStudyPage />} />
            </>
          )}
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}

/** The application in the browser router. */
function App() {
  return (
    <Router>
      <AppRoutes />
    </Router>
  );
}

export default App;
