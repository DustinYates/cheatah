import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './Layout.css';

export default function Layout() {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="layout">
      <nav className="sidebar">
        <div className="logo">
          <h2>Chatter Cheetah</h2>
        </div>
        <ul className="nav-links">
          <li>
            <NavLink to="/" end>Dashboard</NavLink>
          </li>
          <li>
            <NavLink to="/prompts">Prompts</NavLink>
          </li>
          <li>
            <NavLink to="/contacts">Contacts</NavLink>
          </li>
        </ul>
        <button className="logout-btn" onClick={handleLogout}>
          Logout
        </button>
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
