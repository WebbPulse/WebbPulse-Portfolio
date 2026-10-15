import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { CaseStudy, Home, Privacy, NotFound } from './pages';
import { UnderConstruction } from './pages/UnderConstruction';
import { ErrorBoundary } from './components/common';
import { BlogList } from './components/sections/BlogList';
import { BlogPost } from './components/sections/BlogPost';
import './styles/globals.css';

const UNDER_CONSTRUCTION = false;

/**
 * The route table, or the holding page when the site is switched off. Shared
 * by the browser router and the build-time prerender.
 */
export function AppRoutes() {
  return (
    <ErrorBoundary>
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
            <Route path="/blog" element={<BlogList />} />
            <Route path="/blog/:slug" element={<BlogPost />} />
            <Route path="/work/:slug" element={<CaseStudy />} />
          </>
        )}
        <Route path="/privacy" element={<Privacy />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
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
