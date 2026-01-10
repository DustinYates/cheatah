import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { LoadingState, ErrorState, EmptyState } from '../components/ui';

const API_BASE = '/api/v1';

const ASSET_TYPES = [
  { key: 'registration_link', label: 'Registration Link', description: 'Link to registration or sign-up page' },
  { key: 'schedule', label: 'Schedule', description: 'Class times, availability, or calendar' },
  { key: 'pricing', label: 'Pricing', description: 'Pricing information, rates, or packages' },
  { key: 'info', label: 'General Info', description: 'Brochures, details, or general information' },
];

const defaultAsset = {
  sms_template: '',
  url: '',
  enabled: true,
};

export default function SendableAssets() {
  const { token, user, selectedTenantId } = useAuth();
  const [assets, setAssets] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState({});
  const [message, setMessage] = useState({ type: '', text: '' });
  const [editingAsset, setEditingAsset] = useState(null);
  const [editForm, setEditForm] = useState({ ...defaultAsset, asset_type: '' });

  useEffect(() => {
    fetchAssets();
  }, [token, selectedTenantId]);

  const getHeaders = () => {
    const headers = { 'Authorization': `Bearer ${token}` };
    if (user?.is_global_admin && selectedTenantId) {
      headers['X-Tenant-Id'] = selectedTenantId.toString();
    }
    return headers;
  };

  const fetchAssets = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/sendable-assets/assets`, {
        headers: getHeaders(),
      });
      if (response.ok) {
        const data = await response.json();
        setAssets(data.assets || {});
      } else if (response.status === 404) {
        setAssets({});
      } else {
        const errorData = await response.json().catch(() => ({}));
        setError(errorData.detail || 'Failed to load sendable assets');
      }
    } catch (err) {
      console.error('Error fetching sendable assets:', err);
      setError(err.message || 'Failed to load sendable assets');
    } finally {
      setLoading(false);
    }
  };

  const saveAsset = async (assetType) => {
    setSaving((prev) => ({ ...prev, [assetType]: true }));
    setMessage({ type: '', text: '' });

    try {
      const response = await fetch(`${API_BASE}/sendable-assets/assets/${assetType}`, {
        method: 'PUT',
        headers: {
          ...getHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          asset_type: assetType,
          sms_template: editForm.sms_template,
          url: editForm.url,
          enabled: editForm.enabled,
        }),
      });

      if (response.ok) {
        setAssets((prev) => ({
          ...prev,
          [assetType]: {
            sms_template: editForm.sms_template,
            url: editForm.url,
            enabled: editForm.enabled,
          },
        }));
        setMessage({ type: 'success', text: `${ASSET_TYPES.find(t => t.key === assetType)?.label} saved successfully!` });
        setEditingAsset(null);
      } else {
        const errorData = await response.json();
        setMessage({ type: 'error', text: errorData.detail || 'Failed to save asset' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error. Please try again.' });
    } finally {
      setSaving((prev) => ({ ...prev, [assetType]: false }));
    }
  };

  const deleteAsset = async (assetType) => {
    if (!confirm(`Are you sure you want to delete this ${ASSET_TYPES.find(t => t.key === assetType)?.label}?`)) {
      return;
    }

    setSaving((prev) => ({ ...prev, [assetType]: true }));
    setMessage({ type: '', text: '' });

    try {
      const response = await fetch(`${API_BASE}/sendable-assets/assets/${assetType}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });

      if (response.ok) {
        setAssets((prev) => {
          const newAssets = { ...prev };
          delete newAssets[assetType];
          return newAssets;
        });
        setMessage({ type: 'success', text: `${ASSET_TYPES.find(t => t.key === assetType)?.label} deleted successfully!` });
      } else {
        const errorData = await response.json();
        setMessage({ type: 'error', text: errorData.detail || 'Failed to delete asset' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Network error. Please try again.' });
    } finally {
      setSaving((prev) => ({ ...prev, [assetType]: false }));
    }
  };

  const startEditing = (assetType) => {
    const existing = assets[assetType];
    const defaultTemplate = "Hi {name}! Here's the link you requested: {url}";
    setEditForm({
      asset_type: assetType,
      sms_template: existing?.sms_template || defaultTemplate,
      url: existing?.url || '',
      enabled: existing?.enabled ?? true,
    });
    setEditingAsset(assetType);
  };

  const cancelEditing = () => {
    setEditingAsset(null);
    setEditForm({ ...defaultAsset, asset_type: '' });
  };

  const needsTenant = user?.is_global_admin && !selectedTenantId;

  if (needsTenant) {
    return (
      <div className="page-container sendable-assets">
        <EmptyState
          icon="📨"
          title="Select a tenant to manage sendable assets"
          description="Please select a tenant from the dropdown above to manage their sendable assets."
        />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="page-container sendable-assets">
        <LoadingState message="Loading sendable assets..." fullPage />
      </div>
    );
  }

  if (error) {
    if (error.includes('Tenant context required') || error.includes('Tenant context')) {
      return (
        <div className="page-container sendable-assets">
          <EmptyState
            icon="📨"
            title="Select a tenant to manage sendable assets"
            description="Please select a tenant from the dropdown above to manage their sendable assets."
          />
        </div>
      );
    }
    return (
      <div className="page-container sendable-assets">
        <ErrorState message={error} onRetry={fetchAssets} />
      </div>
    );
  }

  return (
    <div className="page-container sendable-assets">
      <div className="page-header">
        <span className="page-title">Sendable Assets</span>
        <p className="page-subtitle">
          Configure links and content that the AI can promise to send via SMS. When the AI says
          "I'll text you the registration link", these assets are automatically sent.
        </p>
      </div>

      {message.text && (
        <div className={`alert ${message.type === 'error' ? 'alert-error' : 'alert-success'}`}>
          {message.text}
        </div>
      )}

      <div className="assets-grid">
        {ASSET_TYPES.map((assetType) => {
          const asset = assets[assetType.key];
          const isEditing = editingAsset === assetType.key;
          const isSaving = saving[assetType.key];

          return (
            <div key={assetType.key} className={`asset-card ${asset ? 'configured' : 'unconfigured'}`}>
              <div className="asset-header">
                <div className="asset-title">
                  <span className="asset-name">{assetType.label}</span>
                  {asset && (
                    <span className={`asset-status ${asset.enabled ? 'enabled' : 'disabled'}`}>
                      {asset.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  )}
                </div>
                <p className="asset-description">{assetType.description}</p>
              </div>

              {isEditing ? (
                <div className="asset-form">
                  <div className="form-group">
                    <label htmlFor={`url-${assetType.key}`}>URL</label>
                    <input
                      id={`url-${assetType.key}`}
                      type="url"
                      value={editForm.url}
                      onChange={(e) => setEditForm({ ...editForm, url: e.target.value })}
                      placeholder="https://example.com/register"
                    />
                  </div>

                  <div className="form-group">
                    <label htmlFor={`template-${assetType.key}`}>SMS Template</label>
                    <textarea
                      id={`template-${assetType.key}`}
                      value={editForm.sms_template}
                      onChange={(e) => setEditForm({ ...editForm, sms_template: e.target.value })}
                      placeholder="Hi {name}! Here's the link you requested: {url}"
                      rows={3}
                    />
                    <span className="help-text">
                      Use {'{name}'} for customer name and {'{url}'} for the link (required).
                    </span>
                  </div>

                  <div className="form-group checkbox-group">
                    <label>
                      <input
                        type="checkbox"
                        checked={editForm.enabled}
                        onChange={(e) => setEditForm({ ...editForm, enabled: e.target.checked })}
                      />
                      Enabled
                    </label>
                  </div>

                  <div className="form-actions">
                    <button
                      className="btn btn-primary"
                      onClick={() => saveAsset(assetType.key)}
                      disabled={isSaving || !editForm.url || !editForm.sms_template.includes('{url}')}
                    >
                      {isSaving ? 'Saving...' : 'Save'}
                    </button>
                    <button className="btn btn-secondary" onClick={cancelEditing} disabled={isSaving}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : asset ? (
                <div className="asset-content">
                  <div className="asset-field">
                    <span className="field-label">URL:</span>
                    <a href={asset.url} target="_blank" rel="noopener noreferrer" className="field-value link">
                      {asset.url}
                    </a>
                  </div>
                  <div className="asset-field">
                    <span className="field-label">SMS Template:</span>
                    <span className="field-value template">{asset.sms_template}</span>
                  </div>
                  <div className="asset-actions">
                    <button className="btn btn-secondary" onClick={() => startEditing(assetType.key)}>
                      Edit
                    </button>
                    <button
                      className="btn btn-danger"
                      onClick={() => deleteAsset(assetType.key)}
                      disabled={isSaving}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ) : (
                <div className="asset-empty">
                  <p>Not configured</p>
                  <button className="btn btn-primary" onClick={() => startEditing(assetType.key)}>
                    Configure
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <style>{`
        .page-container.sendable-assets {
          max-width: 1000px;
          margin: 0 auto;
          padding: 1rem 1.25rem 1.5rem;
        }

        .page-header {
          margin-bottom: 1rem;
        }

        .page-title {
          font-size: 1rem;
          font-weight: 600;
          color: #1a1a1a;
        }

        .page-subtitle {
          font-size: 0.85rem;
          color: #666;
          margin: 0.5rem 0 0;
          line-height: 1.4;
        }

        .alert {
          padding: 0.5rem 0.75rem;
          border-radius: 6px;
          margin-bottom: 0.75rem;
          font-size: 0.9rem;
        }

        .alert-success {
          background: #e6f4ea;
          color: #1e7e34;
        }

        .alert-error {
          background: #fce8e6;
          color: #c5221f;
        }

        .assets-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 1rem;
        }

        .asset-card {
          background: #fff;
          border-radius: 8px;
          padding: 1rem;
          box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
          border: 1px solid #eee;
        }

        .asset-card.configured {
          border-color: #34a853;
        }

        .asset-card.unconfigured {
          border-color: #ddd;
          background: #fafafa;
        }

        .asset-header {
          margin-bottom: 0.75rem;
        }

        .asset-title {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          flex-wrap: wrap;
        }

        .asset-name {
          font-size: 0.95rem;
          font-weight: 600;
          color: #1a1a1a;
        }

        .asset-status {
          font-size: 0.75rem;
          padding: 0.15rem 0.5rem;
          border-radius: 12px;
          font-weight: 500;
        }

        .asset-status.enabled {
          background: #e6f4ea;
          color: #1e7e34;
        }

        .asset-status.disabled {
          background: #fef7e0;
          color: #b45309;
        }

        .asset-description {
          font-size: 0.8rem;
          color: #666;
          margin: 0.25rem 0 0;
        }

        .asset-form {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .form-group {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }

        .form-group label {
          font-size: 0.85rem;
          font-weight: 500;
          color: #444;
        }

        .form-group input[type="url"],
        .form-group textarea {
          padding: 0.45rem 0.5rem;
          border: 1px solid #ddd;
          border-radius: 6px;
          font-size: 0.9rem;
          font-family: inherit;
          color: #333;
        }

        .form-group textarea {
          resize: none;
        }

        .form-group input:focus,
        .form-group textarea:focus {
          outline: none;
          border-color: #4285f4;
          box-shadow: 0 0 0 2px rgba(66, 133, 244, 0.16);
        }

        .checkbox-group label {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          cursor: pointer;
          font-weight: 400;
        }

        .checkbox-group input[type="checkbox"] {
          width: 16px;
          height: 16px;
        }

        .help-text {
          font-size: 0.75rem;
          color: #888;
        }

        .form-actions {
          display: flex;
          gap: 0.5rem;
          margin-top: 0.25rem;
        }

        .asset-content {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .asset-field {
          display: flex;
          flex-direction: column;
          gap: 0.15rem;
        }

        .field-label {
          font-size: 0.75rem;
          font-weight: 500;
          color: #666;
          text-transform: uppercase;
        }

        .field-value {
          font-size: 0.85rem;
          color: #333;
        }

        .field-value.link {
          color: #4285f4;
          text-decoration: none;
          word-break: break-all;
        }

        .field-value.link:hover {
          text-decoration: underline;
        }

        .field-value.template {
          background: #f5f5f5;
          padding: 0.35rem 0.5rem;
          border-radius: 4px;
          font-family: monospace;
          font-size: 0.8rem;
        }

        .asset-actions {
          display: flex;
          gap: 0.5rem;
          margin-top: 0.5rem;
        }

        .asset-empty {
          text-align: center;
          padding: 0.5rem 0;
        }

        .asset-empty p {
          font-size: 0.85rem;
          color: #888;
          margin-bottom: 0.5rem;
        }

        .btn {
          padding: 0.4rem 0.75rem;
          border: none;
          border-radius: 6px;
          font-size: 0.85rem;
          font-weight: 500;
          cursor: pointer;
          transition: background-color 0.2s;
        }

        .btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .btn-primary {
          background: #4285f4;
          color: white;
        }

        .btn-primary:hover:not(:disabled) {
          background: #3367d6;
        }

        .btn-secondary {
          background: #f1f3f4;
          color: #333;
        }

        .btn-secondary:hover:not(:disabled) {
          background: #e8eaed;
        }

        .btn-danger {
          background: #fce8e6;
          color: #c5221f;
        }

        .btn-danger:hover:not(:disabled) {
          background: #f8d7da;
        }

        @media (max-width: 600px) {
          .assets-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
}
