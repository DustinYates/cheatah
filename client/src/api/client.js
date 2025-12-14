const API_BASE = '/api/v1';

class ApiClient {
  constructor() {
    this.token = localStorage.getItem('token');
  }

  setToken(token) {
    this.token = token;
    if (token) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
  }

  async request(endpoint, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    
    // Add tenant override header for global admin impersonation
    const selectedTenant = this.getSelectedTenant();
    const userInfo = this.getUserInfo();
    if (userInfo?.is_global_admin && selectedTenant) {
      headers['X-Tenant-Id'] = selectedTenant.toString();
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      this.setToken(null);
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  async login(email, password) {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(error.detail || 'Login failed');
    }

    const data = await response.json();
    this.setToken(data.access_token);
    // Store user info in localStorage
    localStorage.setItem('userInfo', JSON.stringify({
      email: data.email,
      role: data.role,
      tenant_id: data.tenant_id,
      is_global_admin: data.is_global_admin,
    }));
    return data;
  }

  logout() {
    this.setToken(null);
    localStorage.removeItem('userInfo');
    localStorage.removeItem('selectedTenantId');
  }

  async getMe() {
    return this.request('/auth/me');
  }

  async getTenants() {
    return this.request('/admin/tenants');
  }

  setSelectedTenant(tenantId) {
    if (tenantId) {
      localStorage.setItem('selectedTenantId', tenantId.toString());
    } else {
      localStorage.removeItem('selectedTenantId');
    }
  }

  getSelectedTenant() {
    const id = localStorage.getItem('selectedTenantId');
    return id ? parseInt(id, 10) : null;
  }

  getUserInfo() {
    const info = localStorage.getItem('userInfo');
    return info ? JSON.parse(info) : null;
  }

  async getLeads(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/leads${query ? `?${query}` : ''}`);
  }

  async getLeadsStats() {
    return this.request('/leads/stats');
  }

  async getPromptBundles() {
    return this.request('/prompts/bundles');
  }

  async getPromptBundle(bundleId) {
    return this.request(`/prompts/bundles/${bundleId}`);
  }

  async createPromptBundle(data) {
    return this.request('/prompts/bundles', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updatePromptBundle(bundleId, data) {
    return this.request(`/prompts/bundles/${bundleId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async publishPromptBundle(bundleId) {
    return this.request(`/prompts/bundles/${bundleId}/publish`, {
      method: 'PUT',
    });
  }

  async deletePromptBundle(bundleId) {
    const headers = {
      'Content-Type': 'application/json',
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    
    const selectedTenant = this.getSelectedTenant();
    const userInfo = this.getUserInfo();
    if (userInfo?.is_global_admin && selectedTenant) {
      headers['X-Tenant-Id'] = selectedTenant.toString();
    }

    const response = await fetch(`${API_BASE}/prompts/bundles/${bundleId}`, {
      method: 'DELETE',
      headers,
    });

    if (response.status === 401) {
      this.setToken(null);
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Delete failed' }));
      throw new Error(error.detail || 'Delete failed');
    }

    return true;
  }

  async testPrompt(bundleId, message) {
    return this.request('/prompts/test', {
      method: 'POST',
      body: JSON.stringify({ bundle_id: bundleId, message }),
    });
  }

  async getComposedPrompt(useDraft = false) {
    return this.request(`/prompts/compose${useDraft ? '?use_draft=true' : ''}`);
  }

  async getContacts(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/contacts${query ? `?${query}` : ''}`);
  }

  async getBusinessProfile() {
    return this.request('/tenant/profile');
  }

  async updateBusinessProfile(data) {
    return this.request('/tenant/profile', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }
}

export const api = new ApiClient();
