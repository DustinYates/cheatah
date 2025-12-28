import { useState } from 'react';
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import './Layout.css';

export default function Layout() {
  const { user, logout, tenants, selectedTenantId, selectTenant } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [analyticsOpen, setAnalyticsOpen] = useState(location.pathname.startsWith('/analytics'));

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleTenantChange = (e) => {
    const value = e.target.value;
    selectTenant(value ? parseInt(value, 10) : null);
  };

  const selectedTenant = tenants.find(t => t.id === selectedTenantId);

  return (
    <div className="layout">
      {user?.is_global_admin && selectedTenantId && (
        <div className="impersonation-banner">
          Viewing as: <strong>{selectedTenant?.name || 'Unknown Tenant'}</strong>
          <button onClick={() => selectTenant(null)} className="exit-btn">Exit</button>
        </div>
      )}
      <nav className="sidebar">
        <div className="logo">
          <h2>🐆 Chatter Cheetah</h2>
        </div>
        
        {user?.is_global_admin && (
          <div className="tenant-selector">
            <label>Switch Tenant</label>
            <select value={selectedTenantId || ''} onChange={handleTenantChange}>
              <option value="">-- Master Admin View --</option>
              {tenants.map(tenant => (
                <option key={tenant.id} value={tenant.id}>
                  {tenant.name}
                </option>
              ))}
            </select>
          </div>
        )}
        
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
          <li>
            <NavLink to="/calls">Calls</NavLink>
          </li>
          <li className="nav-section">
            <button
              className={`nav-section-toggle ${analyticsOpen ? 'open' : ''}`}
              onClick={() => setAnalyticsOpen(!analyticsOpen)}
            >
              Analytics
              <span className="toggle-icon">{analyticsOpen ? '−' : '+'}</span>
            </button>
            {analyticsOpen && (
              <ul className="nav-submenu">
                <li>
                  <NavLink to="/analytics/unknowns">Unknowns</NavLink>
                </li>
                <li>
                  <NavLink to="/analytics/plots">Plots</NavLink>
                </li>
              </ul>
            )}
          </li>
          <li>
            <NavLink to="/sms">SMS</NavLink>
          </li>
          <li>
            <NavLink to="/email">Email</NavLink>
          </li>
          <li>
            <NavLink to="/settings">Settings</NavLink>
          </li>
          {user?.is_global_admin && !selectedTenantId && (
            <li>
              <NavLink to="/admin/tenants">Manage Tenants</NavLink>
            </li>
          )}
        </ul>
        <div className="user-info">
          <span className="user-email">{user?.email}</span>
          {user?.is_global_admin && <span className="admin-badge">Admin</span>}
        </div>
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
