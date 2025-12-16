import { createContext, useContext, useState, useEffect } from 'react';
import { api } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileComplete, setProfileComplete] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [selectedTenantId, setSelectedTenantId] = useState(null);

  const loadProfile = async () => {
    try {
      setProfileLoading(true);
      const profile = await api.getBusinessProfile();
      setProfileComplete(profile.profile_complete);
    } catch (err) {
      console.error('Failed to load profile:', err);
      setProfileComplete(false);
    } finally {
      setProfileLoading(false);
    }
  };

  useEffect(() => {
    const initializeAuth = async () => {
      const token = localStorage.getItem('token');
      if (token) {
        try {
          // Set token in API client before making request
          api.setToken(token);
          
          // Verify token is valid by calling /auth/me
          const userData = await api.getMe();
          
          // Build user object from API response
          const userInfo = {
            authenticated: true,
            id: userData.id,
            email: userData.email,
            role: userData.role,
            tenant_id: userData.tenant_id,
            is_global_admin: userData.is_global_admin,
          };
          
          // Update localStorage userInfo to keep it in sync
          localStorage.setItem('userInfo', JSON.stringify({
            email: userData.email,
            role: userData.role,
            tenant_id: userData.tenant_id,
            is_global_admin: userData.is_global_admin,
          }));
          
          setUser(userInfo);
          
          // Restore selected tenant for global admins
          if (userData.is_global_admin) {
            const savedTenant = api.getSelectedTenant();
            setSelectedTenantId(savedTenant);
            try {
              const tenantList = await api.getTenants();
              setTenants(tenantList);
            } catch (err) {
              console.error('Failed to fetch tenants:', err);
            }
            setProfileComplete(true);
          } else {
            // Load profile for tenant users
            await loadProfile();
          }
        } catch (err) {
          // Token is invalid or expired
          console.error('Failed to verify token:', err);
          // Clear auth state (API client already cleared token on 401)
          setUser(null);
          setTenants([]);
          setSelectedTenantId(null);
          setProfileComplete(null);
        }
      }
      setLoading(false);
    };

    initializeAuth();
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
    
    // If global admin, fetch tenants list and skip profile check
    if (data.is_global_admin) {
      setProfileComplete(true);
      try {
        const tenantList = await api.getTenants();
        setTenants(tenantList);
      } catch (err) {
        console.error('Failed to fetch tenants:', err);
      }
    } else {
      // Load profile for tenant users
      await loadProfile();
    }
  };

  const logout = () => {
    api.logout();
    setUser(null);
    setTenants([]);
    setSelectedTenantId(null);
    setProfileComplete(null);
  };

  const selectTenant = (tenantId) => {
    setSelectedTenantId(tenantId);
    api.setSelectedTenant(tenantId);
  };

  const refreshProfile = async () => {
    await loadProfile();
  };

  // Get effective tenant ID (selected tenant for global admin, or user's tenant)
  const effectiveTenantId = user?.is_global_admin ? selectedTenantId : user?.tenant_id;

  return (
    <AuthContext.Provider value={{ 
      user, 
      login, 
      logout, 
      loading,
      profileLoading,
      profileComplete,
      refreshProfile,
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
