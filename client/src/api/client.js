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
    return data;
  }

  logout() {
    this.setToken(null);
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
}

export const api = new ApiClient();
