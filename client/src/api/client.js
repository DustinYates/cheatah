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
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);

    const response = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData,
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

  async getPrompts() {
    return this.request('/prompts');
  }

  async createPrompt(data) {
    return this.request('/prompts', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async testPrompt(promptId, testInput) {
    return this.request(`/prompts/${promptId}/test`, {
      method: 'POST',
      body: JSON.stringify({ input: testInput }),
    });
  }

  async getContacts(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/contacts${query ? `?${query}` : ''}`);
  }
}

export const api = new ApiClient();
