import { useState, useEffect } from 'react';
import { NavLink, Outlet, useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { api } from '../api/client';
import './Layout.css';

export default function Layout() {
  const { user, logout, tenants, selectedTenantId, selectTenant } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [analyticsOpen, setAnalyticsOpen] = useState(location.pathname.startsWith('/analytics'));
  const [communicationsOpen, setCommunicationsOpen] = useState(
    location.pathname.startsWith('/calls')
  );
  const [settingsOpen, setSettingsOpen] = useState(location.pathname.startsWith('/settings'));
  const [forumsOpen, setForumsOpen] = useState(location.pathname.startsWith('/forums'));
  const [hasForumAccess, setHasForumAccess] = useState(false);

  // Check if user has forum access
  useEffect(() => {
    const checkForumAccess = async () => {
      try {
        const forums = await api.getMyForums();
        setHasForumAccess(forums && forums.length > 0);
      } catch (err) {
        setHasForumAccess(false);
      }
    };
    if (user) {
      checkForumAccess();
    }
  }, [user]);

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
          <svg className="logo-mark" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="1" y="1" width="26" height="26" rx="7" fill="url(#sidebar-gradient)"/>
            <path d="M8 10.5C8 9.67 8.67 9 9.5 9h9c.83 0 1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5H13l-2.5 2.5V17H9.5c-.83 0-1.5-.67-1.5-1.5v-5z" fill="rgba(255,255,255,0.95)"/>
            <circle cx="11.5" cy="13" r="1" fill="#6366f1"/>
            <circle cx="14" cy="13" r="1" fill="#6366f1"/>
            <circle cx="16.5" cy="13" r="1" fill="#6366f1"/>
            <defs>
              <linearGradient id="sidebar-gradient" x1="1" y1="1" x2="27" y2="27" gradientUnits="userSpaceOnUse">
                <stop stopColor="#6366f1"/>
                <stop offset="1" stopColor="#8b5cf6"/>
              </linearGradient>
            </defs>
          </svg>
          <h2>ConvoPro</h2>
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
            <NavLink to="/" end>Leads</NavLink>
          </li>
          <li>
            <NavLink to="/kanban">Pipeline</NavLink>
          </li>
          <li>
            <NavLink to="/connections">Connections</NavLink>
          </li>
          <li className="nav-section">
            <button
              className={`nav-section-toggle ${communicationsOpen ? 'open' : ''}`}
              onClick={() => setCommunicationsOpen(!communicationsOpen)}
            >
              Communications
              <span className={`toggle-chevron ${communicationsOpen ? 'open' : ''}`}>&#x203A;</span>
            </button>
            {communicationsOpen && (
              <ul className="nav-submenu">
                <li>
                  <NavLink to="/calls">Calls</NavLink>
                </li>
              </ul>
            )}
          </li>
          <li className="nav-section">
            <button
              className={`nav-section-toggle ${analyticsOpen ? 'open' : ''}`}
              onClick={() => setAnalyticsOpen(!analyticsOpen)}
            >
              Analytics
              <span className={`toggle-chevron ${analyticsOpen ? 'open' : ''}`}>&#x203A;</span>
            </button>
            {analyticsOpen && (
              <ul className="nav-submenu">
                <li>
                  <NavLink to="/analytics/usage">Usage</NavLink>
                </li>
                <li>
                  <NavLink to="/analytics/conversations">Conversations</NavLink>
                </li>
                <li>
                  <NavLink to="/analytics/widget">Widget</NavLink>
                </li>
                <li>
                  <NavLink to="/analytics/savings">Savings</NavLink>
                </li>
                <li>
                  <NavLink to="/analytics/health">Health</NavLink>
                </li>
{user?.is_global_admin && (
                  <li>
                    <NavLink to="/analytics/topics">Topics</NavLink>
                  </li>
                )}
                {user?.is_global_admin && (
                  <li>
                    <NavLink to="/analytics/happiness">Happiness (CHI)</NavLink>
                  </li>
                )}
                {user?.is_global_admin && (
                  <li>
                    <NavLink to="/analytics/voice-ab">Voice Agent A/B</NavLink>
                  </li>
                )}
              </ul>
            )}
          </li>
          <li>
            <NavLink to="/billing">Billing</NavLink>
          </li>
          <li>
            <NavLink to="/support">Support</NavLink>
          </li>
          <li className="nav-section">
            <button
              className={`nav-section-toggle ${settingsOpen ? 'open' : ''}`}
              onClick={() => setSettingsOpen(!settingsOpen)}
            >
              Settings
              <span className={`toggle-chevron ${settingsOpen ? 'open' : ''}`}>&#x203A;</span>
            </button>
            {settingsOpen && (
              <ul className="nav-submenu">
                {user?.is_global_admin && (
                  <li>
                    <NavLink to="/settings/prompts">Prompt</NavLink>
                  </li>
                )}
                <li>
                  <NavLink to="/settings/chatbot">Chatbot</NavLink>
                </li>
                <li>
                  <NavLink to="/settings/email">Email</NavLink>
                </li>
                <li>
                  <NavLink to="/settings/calendar">Calendar</NavLink>
                </li>
                <li>
                  <NavLink to="/settings/sms">SMS Settings</NavLink>
                </li>
                <li>
                  <NavLink to="/settings/escalation">Escalations</NavLink>
                </li>
                <li>
                  <NavLink to="/settings/campaigns">Campaigns</NavLink>
                </li>
                <li>
                  <NavLink to="/settings/dnc">Do Not Contact</NavLink>
                </li>
                {user?.is_global_admin && (
                <li>
                  <NavLink to="/settings/customer-support">Customer Support</NavLink>
                </li>
                )}
                {user?.is_global_admin && (
                  <li>
                    <NavLink to="/settings/telephony">Telephony</NavLink>
                  </li>
                )}
                <li>
                  <NavLink to="/settings/profile">Business Profile</NavLink>
                </li>
                <li>
                  <NavLink to="/settings/account">Account</NavLink>
                </li>
              </ul>
            )}
          </li>
          {hasForumAccess && (
            <li className="nav-section">
              <button
                className={`nav-section-toggle ${forumsOpen ? 'open' : ''}`}
                onClick={() => setForumsOpen(!forumsOpen)}
              >
                Forums
                <span className={`toggle-chevron ${forumsOpen ? 'open' : ''}`}>&#x203A;</span>
              </button>
              {forumsOpen && (
                <ul className="nav-submenu">
                  <li>
                    <NavLink to="/forums">Browse Forums</NavLink>
                  </li>
                </ul>
              )}
            </li>
          )}
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
        <footer className="app-footer">
          <span className="footer-copyright">&copy; {new Date().getFullYear()} ConvoPro</span>
          <span className="footer-divider">&middot;</span>
          <Link to="/privacy">Privacy Policy</Link>
          <span className="footer-divider">&middot;</span>
          <Link to="/terms">Terms of Service</Link>
        </footer>
      </main>
    </div>
  );
}
