const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

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
      localStorage.removeItem('userInfo');
      localStorage.removeItem('selectedTenantId');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  async requestFormData(endpoint, formData, options = {}) {
    const headers = {
      ...options.headers,
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const selectedTenant = this.getSelectedTenant();
    const userInfo = this.getUserInfo();
    if (userInfo?.is_global_admin && selectedTenant) {
      headers['X-Tenant-Id'] = selectedTenant.toString();
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: options.method || 'POST',
      body: formData,
      headers,
    });

    if (response.status === 401) {
      this.setToken(null);
      localStorage.removeItem('userInfo');
      localStorage.removeItem('selectedTenantId');
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
    const response = await this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    
    if (response.access_token) {
      this.setToken(response.access_token);
      localStorage.setItem('userInfo', JSON.stringify({
        tenant_id: response.tenant_id,
        role: response.role,
        email: response.email,
        is_global_admin: response.is_global_admin,
      }));
    }
    
    return response;
  }

  logout() {
    this.setToken(null);
    localStorage.removeItem('userInfo');
    localStorage.removeItem('selectedTenantId');
  }

  async getMe() {
    return this.request('/auth/me');
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

  async getTenants() {
    return this.request('/admin/tenants');
  }

  async getTenantsOverview() {
    return this.request('/admin/tenants/overview');
  }

  async createTenant(tenantData) {
    return this.request('/admin/tenants', {
      method: 'POST',
      body: JSON.stringify(tenantData),
    });
  }

  async updateTenant(tenantId, updates) {
    return this.request(`/admin/tenants/${tenantId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  }

  async getJackrabbitKeys(tenantId) {
    return this.request(`/admin/tenants/${tenantId}/jackrabbit-keys`);
  }

  async updateJackrabbitKeys(tenantId, keys) {
    return this.request(`/admin/tenants/${tenantId}/jackrabbit-keys`, {
      method: 'PUT',
      body: JSON.stringify(keys),
    });
  }

  async deleteJackrabbitKey(tenantId, keyNumber) {
    return this.request(`/admin/tenants/${tenantId}/jackrabbit-keys/${keyNumber}`, {
      method: 'DELETE',
    });
  }

  async getLeads(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/leads${query ? `?${query}` : ''}`);
  }

  async getLead(leadId) {
    return this.request(`/leads/${leadId}`);
  }

  async getLeadConversation(leadId) {
    return this.request(`/leads/${leadId}/conversation`);
  }

  async getRelatedLeads(leadId) {
    return this.request(`/leads/${leadId}/related`);
  }

  async getLeadsStats() {
    return this.request('/leads/stats');
  }

  async getUsageAnalytics(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/analytics/usage${query ? `?${query}` : ''}`);
  }

  async getConversationAnalytics(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/analytics/conversations${query ? `?${query}` : ''}`);
  }

  async getWidgetAnalytics(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/analytics/widget${query ? `?${query}` : ''}`);
  }

  async getWidgetSettingsSnapshots(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/analytics/widget/settings-snapshots${query ? `?${query}` : ''}`);
  }

  async getSavingsAnalytics(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/analytics/savings${query ? `?${query}` : ''}`);
  }

  async getTopicAnalytics(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/analytics/topics${query ? `?${query}` : ''}`);
  }

  async revealTelephonyCredential(field) {
    return this.request('/admin/telephony/credentials/reveal', {
      method: 'POST',
      body: JSON.stringify({ field }),
    });
  }

  async auditTelephonyCredentialAction(action, field) {
    return this.request('/admin/telephony/credentials/audit', {
      method: 'POST',
      body: JSON.stringify({ action, field }),
    });
  }

  async updateLeadStatus(leadId, status) {
    return this.request(`/leads/${leadId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    });
  }

  async deleteLead(leadId) {
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

    const response = await fetch(`${API_BASE}/leads/${leadId}`, {
      method: 'DELETE',
      headers,
    });

    if (response.status === 401) {
      this.setToken(null);
      localStorage.removeItem('userInfo');
      localStorage.removeItem('selectedTenantId');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (response.status === 204) {
      return true;
    }

    if (!response.ok) {
      let errorMessage = `Delete failed (${response.status})`;
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorData.message || errorMessage;
      } catch (e) {
        // If response is not JSON, try to get text
        try {
          const text = await response.text();
          if (text) {
            errorMessage = text;
          }
        } catch (e2) {
          // Ignore
        }
      }
      throw new Error(errorMessage);
    }

    return true;
  }

  async cleanupTestLeads() {
    return this.request('/leads/cleanup/test-data', {
      method: 'DELETE',
    });
  }

  async triggerFollowUp(leadId) {
    return this.request(`/leads/${leadId}/trigger-followup`, {
      method: 'POST',
    });
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

  async deactivatePromptBundle(bundleId) {
    return this.request(`/prompts/bundles/${bundleId}/deactivate`, {
      method: 'PUT',
    });
  }

  async restorePromptBundle(bundleId) {
    return this.request(`/prompts/bundles/${bundleId}/restore`, {
      method: 'POST',
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
      localStorage.removeItem('userInfo');
      localStorage.removeItem('selectedTenantId');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Delete failed' }));
      throw new Error(error.detail || 'Delete failed');
    }

    return true;
  }

  async testPrompt(bundleId, message, history = []) {
    return this.request('/prompts/test', {
      method: 'POST',
      body: JSON.stringify({ bundle_id: bundleId, message, history }),
    });
  }

  async getComposedPrompt(useDraft = false) {
    return this.request(`/prompts/compose${useDraft ? '?use_draft=true' : ''}`);
  }

  async getVoicePrompt(bundleId) {
    return this.request(`/prompts/bundles/${bundleId}/voice`);
  }

  // V2 Prompt Config methods (JSON-based system)
  async getPromptConfig() {
    return this.request('/prompt-config/config');
  }

  async upsertPromptConfig(config, schemaVersion = 'bss_chatbot_prompt_v1', businessType = 'bss') {
    return this.request('/prompt-config/config', {
      method: 'POST',
      body: JSON.stringify({
        config,
        schema_version: schemaVersion,
        business_type: businessType,
      }),
    });
  }

  async deletePromptConfig() {
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

    const response = await fetch(`${API_BASE}/prompt-config/config`, {
      method: 'DELETE',
      headers,
    });

    if (response.status === 204) {
      return true;
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Delete failed' }));
      throw new Error(error.detail || 'Delete failed');
    }

    return true;
  }

  async previewPromptConfig(channel = 'chat', context = null) {
    return this.request('/prompt-config/preview', {
      method: 'POST',
      body: JSON.stringify({ channel, context }),
    });
  }

  async validatePromptConfig(config, schemaVersion = 'bss_chatbot_prompt_v1', businessType = 'bss') {
    return this.request('/prompt-config/validate', {
      method: 'POST',
      body: JSON.stringify({
        config,
        schema_version: schemaVersion,
        business_type: businessType,
      }),
    });
  }

  async getBaseConfig(businessType = 'bss') {
    return this.request(`/prompt-config/base-config?business_type=${businessType}`);
  }

  // Channel Prompts (Unified Prompt Architecture)
  async getChannelPrompts() {
    return this.request('/prompt-config/channel-prompts');
  }

  async getChannelPrompt(channel) {
    return this.request(`/prompt-config/channel-prompts/${channel}`);
  }

  async setChannelPrompt(channel, prompt) {
    return this.request(`/prompt-config/channel-prompts/${channel}`, {
      method: 'PUT',
      body: JSON.stringify({ prompt }),
    });
  }

  async deleteChannelPrompt(channel) {
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

    const response = await fetch(`${API_BASE}/prompt-config/channel-prompts/${channel}`, {
      method: 'DELETE',
      headers,
    });

    if (response.status === 204) {
      return true;
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Delete failed' }));
      throw new Error(error.detail || 'Delete failed');
    }

    return true;
  }

  async getContacts(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/contacts${query ? `?${query}` : ''}`);
  }

  async getContact(contactId, includeAliases = false) {
    const query = includeAliases ? '?include_aliases=true' : '';
    return this.request(`/contacts/${contactId}${query}`);
  }

  async updateContact(contactId, data) {
    return this.request(`/contacts/${contactId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteContact(contactId) {
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

    const response = await fetch(`${API_BASE}/contacts/${contactId}`, {
      method: 'DELETE',
      headers,
    });

    if (response.status === 401) {
      this.setToken(null);
      localStorage.removeItem('userInfo');
      localStorage.removeItem('selectedTenantId');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (response.status === 204) {
      return true;
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Delete failed' }));
      throw new Error(error.detail || 'Delete failed');
    }

    return true;
  }

  async getContactConversation(contactId) {
    return this.request(`/contacts/${contactId}/conversation`);
  }

  // Contact merge methods
  async getMergePreview(contactIds) {
    return this.request('/contacts/merge-preview', {
      method: 'POST',
      body: JSON.stringify(contactIds),
    });
  }

  async mergeContacts(primaryContactId, secondaryContactIds, fieldResolutions = {}) {
    return this.request(`/contacts/${primaryContactId}/merge`, {
      method: 'POST',
      body: JSON.stringify({
        secondary_contact_ids: secondaryContactIds,
        field_resolutions: fieldResolutions,
      }),
    });
  }

  async getMergeHistory(contactId) {
    return this.request(`/contacts/${contactId}/merge-history`);
  }

  // Contact activity methods
  async getContactActivityHeatmap(contactId, days = 365) {
    return this.request(`/contacts/${contactId}/activity-heatmap?days=${days}`);
  }

  async getContactActivityFeed(contactId, page = 1, pageSize = 20, channel = null) {
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
    });
    if (channel) {
      params.set('channel', channel);
    }
    return this.request(`/contacts/${contactId}/activity-feed?${params}`);
  }

  // Contact alias methods
  async getContactAliases(contactId, aliasType = null) {
    const query = aliasType ? `?alias_type=${aliasType}` : '';
    return this.request(`/contacts/${contactId}/aliases${query}`);
  }

  async addContactAlias(contactId, aliasData) {
    return this.request(`/contacts/${contactId}/aliases`, {
      method: 'POST',
      body: JSON.stringify(aliasData),
    });
  }

  async setPrimaryAlias(contactId, aliasId) {
    return this.request(`/contacts/${contactId}/aliases/${aliasId}/primary`, {
      method: 'PUT',
    });
  }

  async removeContactAlias(contactId, aliasId) {
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

    const response = await fetch(`${API_BASE}/contacts/${contactId}/aliases/${aliasId}`, {
      method: 'DELETE',
      headers,
    });

    if (response.status === 401) {
      this.setToken(null);
      localStorage.removeItem('userInfo');
      localStorage.removeItem('selectedTenantId');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (response.status === 204) {
      return true;
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Delete failed' }));
      throw new Error(error.detail || 'Delete failed');
    }

    return true;
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

  async getEmbedCode() {
    return this.request('/tenants/me/embed-code');
  }

  // Prompt Interview / Wizard methods
  async startPromptInterview() {
    return this.request('/prompts/interview/start');
  }

  async submitInterviewAnswer(data) {
    return this.request('/prompts/interview/answer', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async generatePromptFromInterview(data) {
    return this.request('/prompts/interview/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getInterviewSuggestions() {
    return this.request('/prompts/interview/suggestions');
  }

  async getScrapeStatus() {
    return this.request('/tenant/profile/scrape-status');
  }

  async triggerRescrape() {
    return this.request('/tenant/profile/rescrape', {
      method: 'POST',
    });
  }

  // Calls methods
  async getCalls(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/calls${query ? `?${query}` : ''}`);
  }

  async getCall(callId) {
    return this.request(`/calls/${callId}`);
  }

  async getCallsForContact(contactId, params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/calls/by-contact/${contactId}${query ? `?${query}` : ''}`);
  }

  async getCallsForPhone(phoneNumber, params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/calls/by-phone/${encodeURIComponent(phoneNumber)}${query ? `?${query}` : ''}`);
  }

  // Email settings methods
  async getEmailSettings() {
    return this.request('/email/settings');
  }

  async updateEmailSettings(data) {
    return this.request('/email/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async startEmailOAuth() {
    return this.request('/email/oauth/start', {
      method: 'POST',
    });
  }

  async disconnectEmail() {
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

    const response = await fetch(`${API_BASE}/email/disconnect`, {
      method: 'DELETE',
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Disconnect failed' }));
      throw new Error(error.detail || 'Disconnect failed');
    }

    return response.json();
  }

  async refreshEmailWatch() {
    return this.request('/email/refresh-watch', {
      method: 'POST',
    });
  }

  // SMS settings methods (tenant-facing)
  async getSmsSettings() {
    return this.request('/sms/settings');
  }

  async updateSmsSettings(data) {
    return this.request('/sms/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async getEmailConversations(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/email/conversations${query ? `?${query}` : ''}`);
  }

  async getEmailConversationsForContact(contactId, params = {}) {
    const query = new URLSearchParams({ ...params, contact_id: contactId }).toString();
    return this.request(`/email/conversations${query ? `?${query}` : ''}`);
  }

  // Widget settings methods
  async getWidgetSettings() {
    return this.request('/widget/settings');
  }

  async updateWidgetSettings(data) {
    return this.request('/widget/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async uploadWidgetIcon(file) {
    const formData = new FormData();
    formData.append('file', file);
    return this.requestFormData('/widget/icon/upload', formData);
  }

  async uploadWidgetAsset(file) {
    const formData = new FormData();
    formData.append('file', file);
    return this.requestFormData('/widget/assets', formData);
  }

  // Telephony configuration methods
  async getTelephonyConfig() {
    return this.request('/admin/telephony/config');
  }

  async updateTelephonyConfig(data) {
    return this.request('/admin/telephony/config', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async validateTelephonyCredentials(data) {
    return this.request('/admin/telephony/validate-credentials', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Configuration History methods
  async getConfigHistory(limit = 10) {
    return this.request(`/config/history?limit=${limit}`);
  }

  async getConfigSnapshot(snapshotId) {
    return this.request(`/config/history/${snapshotId}`);
  }

  async getConfigSnapshotByVersionId(versionId) {
    return this.request(`/config/history/by-version/${versionId}`);
  }

  async getConfigDiff(snapshotId, compareToId = null) {
    const query = compareToId ? `?compare_to=${compareToId}` : '';
    return this.request(`/config/history/${snapshotId}/diff${query}`);
  }

  async rollbackToSnapshot(snapshotId) {
    return this.request(`/config/history/${snapshotId}/rollback`, {
      method: 'POST',
    });
  }

  // Calendar settings methods
  async getCalendarSettings() {
    return this.request('/calendar/settings');
  }

  async updateCalendarSettings(data) {
    return this.request('/calendar/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async startCalendarOAuth() {
    return this.request('/calendar/oauth/start', {
      method: 'POST',
    });
  }

  async disconnectCalendar() {
    return this.request('/calendar/disconnect', {
      method: 'DELETE',
    });
  }

  async getCalendarSlots(dateStart, numDays = 3) {
    const params = new URLSearchParams();
    if (dateStart) params.set('date_start', dateStart);
    params.set('num_days', numDays.toString());
    return this.request(`/calendar/available-slots?${params}`);
  }

  async getCalendarEvents(weekOffset = 0) {
    const params = new URLSearchParams();
    if (weekOffset !== 0) params.set('week_offset', weekOffset.toString());
    const qs = params.toString();
    return this.request(`/calendar/events${qs ? `?${qs}` : ''}`);
  }

  async getCalendarList() {
    return this.request('/calendar/calendars');
  }

  // Inbox
  async getInboxConversations(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/inbox/conversations${query ? `?${query}` : ''}`);
  }

  async getInboxConversation(conversationId) {
    return this.request(`/inbox/conversations/${conversationId}`);
  }

  async replyToConversation(conversationId, content) {
    return this.request(`/inbox/conversations/${conversationId}/reply`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  }

  async resolveConversation(conversationId) {
    return this.request(`/inbox/conversations/${conversationId}/resolve`, {
      method: 'POST',
    });
  }

  async reopenConversation(conversationId) {
    return this.request(`/inbox/conversations/${conversationId}/reopen`, {
      method: 'POST',
    });
  }

  async resolveInboxEscalation(escalationId, notes = null) {
    return this.request(`/inbox/escalations/${escalationId}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ notes }),
    });
  }

  // Customers API
  async getCustomers(params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/customers${query ? `?${query}` : ''}`);
  }

  async getCustomer(customerId) {
    return this.request(`/customers/${customerId}`);
  }

  async createCustomer(data) {
    return this.request('/customers', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateCustomer(customerId, data) {
    return this.request(`/customers/${customerId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteCustomer(customerId) {
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

    const response = await fetch(`${API_BASE}/customers/${customerId}`, {
      method: 'DELETE',
      headers,
    });

    if (response.status === 401) {
      this.setToken(null);
      localStorage.removeItem('userInfo');
      localStorage.removeItem('selectedTenantId');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (response.status === 204) {
      return true;
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Delete failed' }));
      throw new Error(error.detail || 'Delete failed');
    }

    return true;
  }

  async searchCustomers(query) {
    return this.request(`/customers/search?q=${encodeURIComponent(query)}`);
  }

  async getCustomerStats() {
    return this.request('/customers/stats');
  }

  // Customer Support Config API
  async getCustomerSupportConfig() {
    return this.request('/customer-support/config');
  }

  async updateCustomerSupportConfig(data) {
    return this.request('/customer-support/config', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  // ==================== Forum API ====================

  async getMyForums() {
    return this.request('/forums/my-forums');
  }

  async getForum(forumSlug) {
    return this.request(`/forums/${forumSlug}`);
  }

  async getForumPosts(forumSlug, categorySlug, params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.request(`/forums/${forumSlug}/${categorySlug}${query ? `?${query}` : ''}`);
  }

  async getForumPost(forumSlug, categorySlug, postId) {
    return this.request(`/forums/${forumSlug}/${categorySlug}/${postId}`);
  }

  async createForumPost(forumSlug, categorySlug, data) {
    return this.request(`/forums/${forumSlug}/${categorySlug}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async togglePostVote(forumSlug, categorySlug, postId) {
    return this.request(`/forums/${forumSlug}/${categorySlug}/${postId}/vote`, {
      method: 'POST',
    });
  }

  async archivePost(forumSlug, categorySlug, postId, data) {
    return this.request(`/forums/${forumSlug}/${categorySlug}/${postId}/archive`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // ==================== User Groups API (Admin) ====================

  async getUserGroups() {
    return this.request('/admin/groups');
  }

  async createUserGroup(data) {
    return this.request('/admin/groups', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getUserGroup(groupId) {
    return this.request(`/admin/groups/${groupId}`);
  }

  async updateUserGroup(groupId, data) {
    return this.request(`/admin/groups/${groupId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteUserGroup(groupId) {
    return this.request(`/admin/groups/${groupId}`, {
      method: 'DELETE',
    });
  }

  async getGroupMembers(groupId) {
    return this.request(`/admin/groups/${groupId}/members`);
  }

  async addGroupMember(groupId, userId, role = 'member') {
    return this.request(`/admin/groups/${groupId}/members`, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role }),
    });
  }

  async removeGroupMember(groupId, userId) {
    return this.request(`/admin/groups/${groupId}/members/${userId}`, {
      method: 'DELETE',
    });
  }

  async searchAvailableUsers(groupId, search = '') {
    return this.request(`/admin/groups/${groupId}/available-users?search=${encodeURIComponent(search)}`);
  }

  async createForumForGroup(groupId, data) {
    return this.request(`/admin/groups/${groupId}/forum`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async createForumCategory(groupId, data) {
    return this.request(`/admin/groups/${groupId}/forum/categories`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }
}

export const api = new ApiClient();
