import { useState, useEffect } from 'react';
import { api } from '../api/client';
import './Prompts.css';

export default function Prompts() {
  const [prompts, setPrompts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [testPromptId, setTestPromptId] = useState(null);
  const [testInput, setTestInput] = useState('');
  const [testResult, setTestResult] = useState('');
  const [testLoading, setTestLoading] = useState(false);
  
  const [newPrompt, setNewPrompt] = useState({
    name: '',
    type: 'greeting',
    content: '',
  });

  useEffect(() => {
    fetchPrompts();
  }, []);

  const fetchPrompts = async () => {
    try {
      const data = await api.getPrompts().catch(() => []);
      setPrompts(Array.isArray(data) ? data : data.prompts || []);
    } catch (err) {
      console.error('Failed to fetch prompts:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      const created = await api.createPrompt(newPrompt);
      setPrompts([created, ...prompts]);
      setNewPrompt({ name: '', type: 'greeting', content: '' });
      setShowCreate(false);
    } catch (err) {
      alert('Failed to create prompt: ' + err.message);
    }
  };

  const handleTest = async (e) => {
    e.preventDefault();
    setTestLoading(true);
    try {
      const result = await api.testPrompt(testPromptId, testInput);
      setTestResult(result.response || result.output || JSON.stringify(result));
    } catch (err) {
      setTestResult('Error: ' + err.message);
    } finally {
      setTestLoading(false);
    }
  };

  if (loading) {
    return <div className="loading">Loading prompts...</div>;
  }

  return (
    <div className="prompts-page">
      <div className="page-header">
        <h1>Prompts</h1>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>
          Create Prompt
        </button>
      </div>

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Create New Prompt</h2>
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>Name</label>
                <input
                  type="text"
                  value={newPrompt.name}
                  onChange={(e) => setNewPrompt({ ...newPrompt, name: e.target.value })}
                  placeholder="e.g., Welcome Message"
                  required
                />
              </div>
              <div className="form-group">
                <label>Type</label>
                <select
                  value={newPrompt.type}
                  onChange={(e) => setNewPrompt({ ...newPrompt, type: e.target.value })}
                >
                  <option value="greeting">Greeting</option>
                  <option value="follow_up">Follow Up</option>
                  <option value="qualification">Qualification</option>
                  <option value="objection">Objection Handling</option>
                  <option value="closing">Closing</option>
                </select>
              </div>
              <div className="form-group">
                <label>Content</label>
                <textarea
                  value={newPrompt.content}
                  onChange={(e) => setNewPrompt({ ...newPrompt, content: e.target.value })}
                  placeholder="Enter your prompt content..."
                  rows={6}
                  required
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowCreate(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {testPromptId && (
        <div className="modal-overlay" onClick={() => { setTestPromptId(null); setTestResult(''); }}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Test Prompt</h2>
            <form onSubmit={handleTest}>
              <div className="form-group">
                <label>Test Input</label>
                <textarea
                  value={testInput}
                  onChange={(e) => setTestInput(e.target.value)}
                  placeholder="Enter test message..."
                  rows={3}
                  required
                />
              </div>
              <button type="submit" className="btn-primary" disabled={testLoading}>
                {testLoading ? 'Testing...' : 'Run Test'}
              </button>
              
              {testResult && (
                <div className="test-result">
                  <label>Result:</label>
                  <pre>{testResult}</pre>
                </div>
              )}
            </form>
            <button className="btn-secondary close-btn" onClick={() => { setTestPromptId(null); setTestResult(''); }}>
              Close
            </button>
          </div>
        </div>
      )}

      <div className="prompts-grid">
        {prompts.length === 0 ? (
          <div className="empty-state">
            <p>No prompts yet. Create your first prompt to get started.</p>
          </div>
        ) : (
          prompts.map((prompt) => (
            <div key={prompt.id} className="prompt-card">
              <div className="prompt-header">
                <h3>{prompt.name}</h3>
                <span className="prompt-type">{prompt.type}</span>
              </div>
              <p className="prompt-content">{prompt.content}</p>
              <div className="prompt-actions">
                <button className="btn-secondary" onClick={() => setTestPromptId(prompt.id)}>
                  Test
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
