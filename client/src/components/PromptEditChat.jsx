import { useState, useRef, useEffect } from 'react';
import { api } from '../api/client';
import './PromptEditChat.css';

export default function PromptEditChat({ bundle, onClose, onUpdate }) {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [sections, setSections] = useState(bundle.sections || []);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    // Initial message
    setMessages([
      {
        type: 'assistant',
        content: `I'll help you edit "${bundle.name}". Tell me what you'd like to change. For example:\n\n• "Remove the cancellation policy"\n• "Change the business hours to 9am-5pm"\n• "Add information about parking"\n• "Make the tone more professional"`,
      },
    ]);
  }, [bundle.name]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const submitEdit = async () => {
    if (!inputValue.trim() || loading) return;

    const instruction = inputValue.trim();
    setMessages(prev => [...prev, { type: 'user', content: instruction }]);
    setInputValue('');
    setLoading(true);

    try {
      const response = await api.editPromptViaChat(bundle.id, {
        edit_instruction: instruction,
      });

      setSections(response.updated_sections);
      setMessages(prev => [...prev, {
        type: 'assistant',
        content: `✅ ${response.changes_made}\n\nWould you like to make any other changes?`,
      }]);

      // Notify parent of update
      if (onUpdate) {
        onUpdate(response.updated_sections);
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        type: 'error',
        content: err.message || 'Failed to apply edit. Please try rephrasing your request.',
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !loading) {
      e.preventDefault();
      submitEdit();
    }
  };

  return (
    <div className="prompt-edit-chat">
      <div className="edit-chat-header">
        <h3>Edit Prompt</h3>
        <button className="close-button" onClick={onClose}>×</button>
      </div>

      <div className="edit-chat-body">
        {/* Current Sections Preview */}
        <div className="sections-preview">
          <h4>Current Sections</h4>
          <div className="sections-list">
            {sections.map((section, idx) => (
              <div key={idx} className="section-preview-item">
                <span className="section-key">{section.section_key}</span>
                <span className="section-preview-content">
                  {section.content?.substring(0, 80)}
                  {section.content?.length > 80 ? '...' : ''}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Chat Messages */}
        <div className="edit-messages">
          {messages.map((msg, idx) => (
            <div key={idx} className={`edit-message ${msg.type}`}>
              {msg.type === 'assistant' && <span className="avatar">🐆</span>}
              <div className="edit-message-content">
                {msg.content.split('\n').map((line, i) => (
                  <p key={i}>{line}</p>
                ))}
              </div>
            </div>
          ))}
          
          {loading && (
            <div className="edit-message assistant">
              <span className="avatar">🐆</span>
              <div className="edit-message-content typing">
                <span></span><span></span><span></span>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="edit-chat-input">
        <textarea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Describe what you'd like to change..."
          disabled={loading}
          rows={2}
        />
        <button 
          onClick={submitEdit}
          disabled={loading || !inputValue.trim()}
        >
          {loading ? '...' : 'Send'}
        </button>
      </div>

      <div className="edit-chat-footer">
        <button className="done-button" onClick={onClose}>
          Done Editing
        </button>
      </div>
    </div>
  );
}
