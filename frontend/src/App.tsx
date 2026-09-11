import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Home, Privacy } from './pages';
import { UnderConstruction } from './pages/UnderConstruction';
import { AdminPanel } from './components/admin/AdminPanel';
import { BlogList } from './components/sections/BlogList';
import { BlogPost } from './components/sections/BlogPost';
import './styles/globals.css';

const UNDER_CONSTRUCTION = false;

function App() {
  return (
    <Router>
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
          </>
        )}
        <Route path="/admin" element={<AdminPanel />} />
        {/*
          Registered outside the under construction switch on purpose. Google's
          OAuth consent screen requires a reachable privacy policy URL, and a
          policy that turned into a placeholder whenever the site was being
          worked on would fail that check at the worst possible moment.
        */}
        <Route path="/privacy" element={<Privacy />} />
      </Routes>
    </Router>
  );
}

export default App;
