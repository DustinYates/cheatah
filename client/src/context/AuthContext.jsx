import { createContext, useContext, useState, useEffect } from 'react';
import { api } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tenants, setTenants] = useState([]);
  const [selectedTenantId, setSelectedTenantId] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      api.setToken(token);
      const userInfo = api.getUserInfo();
      if (userInfo) {
        setUser({ authenticated: true, ...userInfo });
        // Restore selected tenant for global admins
        if (userInfo.is_global_admin) {
          const savedTenant = api.getSelectedTenant();
          setSelectedTenantId(savedTenant);
          // Fetch tenants list
          api.getTenants().then(setTenants).catch(console.error);
        }
      } else {
        setUser({ authenticated: true });
      }
    }
    setLoading(false);
  }, []);

  const login = async (email, password) => {
    const data = await api.login(email, password);
    const userInfo = {
      authenticated: true,
      email: data.email,
      role: data.role,
      tenant_id: data.tenant_id,
      is_global_admin: data.is_global_admin,
    };
    setUser(userInfo);
    
    // If global admin, fetch tenants list
    if (data.is_global_admin) {
      try {
        const tenantList = await api.getTenants();
        setTenants(tenantList);
      } catch (err) {
        console.error('Failed to fetch tenants:', err);
      }
    }
  };

  const logout = () => {
    api.logout();
    setUser(null);
    setTenants([]);
    setSelectedTenantId(null);
  };

  const selectTenant = (tenantId) => {
    setSelectedTenantId(tenantId);
    api.setSelectedTenant(tenantId);
  };

  // Get effective tenant ID (selected tenant for global admin, or user's tenant)
  const effectiveTenantId = user?.is_global_admin ? selectedTenantId : user?.tenant_id;

  return (
    <AuthContext.Provider value={{ 
      user, 
      login, 
      logout, 
      loading, 
      tenants, 
      selectedTenantId, 
      selectTenant,
      effectiveTenantId,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
