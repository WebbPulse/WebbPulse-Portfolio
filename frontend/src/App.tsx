import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Home, Privacy, VerifyEmail, ResetPassword } from './pages';
import { UnderConstruction } from './pages/UnderConstruction';
import { AdminPanel } from './components/admin/AdminPanel';
import { BlogList } from './components/sections/BlogList';
import { BlogPost } from './components/sections/BlogPost';
import './styles/globals.css';

const UNDER_CONSTRUCTION = false;

/** Routes the application, or the holding page when the site is switched off. */
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
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/reset-password" element={<ResetPassword />} />
      </Routes>
    </Router>
  );
}

export default App;
