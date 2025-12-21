import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import './PromptWizard.css';

export default function PromptWizard() {
  const navigate = useNavigate();
  const messagesEndRef = useRef(null);
  
  const [messages, setMessages] = useState([]);
  const [currentStep, setCurrentStep] = useState(null);
  const [questionType, setQuestionType] = useState('text');
  const [choices, setChoices] = useState(null);
  const [collectedData, setCollectedData] = useState({});
  const [inputValue, setInputValue] = useState('');
  const [isComplete, setIsComplete] = useState(false);
  const [progress, setProgress] = useState(0);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [generatedPrompt, setGeneratedPrompt] = useState(null);

  // Start the interview on mount
  useEffect(() => {
    startInterview();
  }, []);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const startInterview = async () => {
    setLoading(true);
    try {
      const response = await api.startPromptInterview();
      setCurrentStep(response.current_step);
      setQuestionType(response.question_type);
      setChoices(response.choices);
      setProgress(response.progress);
      
      // Add welcome message
      setMessages([
        {
          type: 'assistant',
          content: "👋 Hi! I'm going to help you set up your chatbot. I'll ask you a few questions about your business, and then I'll create a customized prompt for your chatbot.",
        },
        {
          type: 'assistant',
          content: response.question,
        },
      ]);
    } catch (err) {
      setError(err.message || 'Failed to start interview');
    } finally {
      setLoading(false);
    }
  };

  const submitAnswer = async (answer) => {
    if (!answer.trim() && questionType === 'text') return;
    
    // Add user message
    const userMessage = questionType === 'choice' 
      ? choices?.find(c => c.value === answer)?.label || answer
      : answer;
    
    setMessages(prev => [...prev, { type: 'user', content: userMessage }]);
    setInputValue('');
    setLoading(true);

    try {
      const response = await api.submitInterviewAnswer({
        current_step: currentStep,
        answer: answer,
        collected_data: collectedData,
      });

      setCurrentStep(response.current_step);
      setQuestionType(response.question_type);
      setChoices(response.choices);
      setCollectedData(response.collected_data);
      setProgress(response.progress);
      setIsComplete(response.is_complete);

      // Add assistant message
      setMessages(prev => [...prev, { type: 'assistant', content: response.question }]);
    } catch (err) {
      setError(err.message || 'Failed to submit answer');
      setMessages(prev => [...prev, { 
        type: 'error', 
        content: 'Something went wrong. Please try again.' 
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !loading) {
      e.preventDefault();
      submitAnswer(inputValue);
    }
  };

  const generatePrompt = async () => {
    setGenerating(true);
    try {
      const response = await api.generatePromptFromInterview({
        collected_data: collectedData,
      });
      
      setGeneratedPrompt(response);
      setMessages(prev => [...prev, { 
        type: 'assistant', 
        content: `✅ ${response.message}` 
      }]);
    } catch (err) {
      setError(err.message || 'Failed to generate prompt');
      setMessages(prev => [...prev, { 
        type: 'error', 
        content: 'Failed to generate prompt. Please try again.' 
      }]);
    } finally {
      setGenerating(false);
    }
  };

  const goToPrompts = () => {
    navigate('/prompts');
  };

  return (
    <div className="prompt-wizard">
      {/* Header */}
      <div className="wizard-header">
        <button className="back-button" onClick={() => navigate('/prompts')}>
          ← Back to Prompts
        </button>
        <div className="wizard-title">
          <h1>Create Your Chatbot</h1>
          <p>Answer a few questions to set up your chatbot's personality and knowledge</p>
        </div>
        <div className="progress-container">
          <div className="progress-bar">
            <div 
              className="progress-fill" 
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="progress-text">{progress}% complete</span>
        </div>
      </div>

      {/* Chat Container */}
      <div className="wizard-chat">
        <div className="messages-container">
          {messages.map((msg, idx) => (
            <div 
              key={idx} 
              className={`message ${msg.type}`}
            >
              {msg.type === 'assistant' && (
                <div className="message-avatar">🐆</div>
              )}
              <div className="message-content">
                {msg.content}
              </div>
            </div>
          ))}
          
          {loading && (
            <div className="message assistant">
              <div className="message-avatar">🐆</div>
              <div className="message-content typing">
                <span></span><span></span><span></span>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="input-area">
          {error && (
            <div className="error-banner">
              {error}
              <button onClick={() => setError(null)}>×</button>
            </div>
          )}
          
          {!isComplete ? (
            questionType === 'choice' && choices ? (
              <div className="choices-container">
                {choices.map((choice) => (
                  <button
                    key={choice.value}
                    className="choice-button"
                    onClick={() => submitAnswer(choice.value)}
                    disabled={loading}
                  >
                    <div className="choice-label">{choice.label}</div>
                    <div className="choice-description">{choice.description}</div>
                    <div className="choice-example">"{choice.example}"</div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="text-input-container">
                <textarea
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Type your answer..."
                  disabled={loading}
                  rows={3}
                />
                <button 
                  className="send-button"
                  onClick={() => submitAnswer(inputValue)}
                  disabled={loading || !inputValue.trim()}
                >
                  Send
                </button>
              </div>
            )
          ) : (
            <div className="complete-actions">
              {!generatedPrompt ? (
                <button 
                  className="generate-button"
                  onClick={generatePrompt}
                  disabled={generating}
                >
                  {generating ? (
                    <>
                      <span className="spinner"></span>
                      Generating...
                    </>
                  ) : (
                    '✨ Generate Prompt'
                  )}
                </button>
              ) : (
                <div className="success-actions">
                  <div className="success-message">
                    <span className="success-icon">✅</span>
                    Prompt created successfully!
                  </div>
                  <div className="action-buttons">
                    <button 
                      className="secondary-button"
                      onClick={goToPrompts}
                    >
                      View All Prompts
                    </button>
                    <button 
                      className="primary-button"
                      onClick={() => navigate(`/prompts?test=${generatedPrompt.bundle_id}`)}
                    >
                      Test Your Chatbot
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Preview Panel (shows collected data) */}
      {Object.keys(collectedData).length > 0 && (
        <div className="preview-panel">
          <h3>📋 Collected Information</h3>
          <div className="collected-data">
            {Object.entries(collectedData).map(([key, value]) => (
              <div key={key} className="data-item">
                <span className="data-label">{formatLabel(key)}:</span>
                <span className="data-value">{formatValue(key, value)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Helper functions
function formatLabel(key) {
  const labels = {
    business_name: 'Business Name',
    industry: 'Industry',
    location: 'Location',
    phone_number: 'Phone',
    website_url: 'Website',
    business_hours: 'Hours',
    services: 'Services',
    pricing: 'Pricing',
    faq: 'FAQ',
    policies: 'Policies',
    requirements: 'Requirements',
    tone: 'Tone',
    lead_timing: 'Lead Capture',
    anything_else: 'Additional',
  };
  return labels[key] || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatValue(key, value) {
  if (key === 'tone') {
    const tones = {
      friendly_casual: 'Friendly & Casual',
      professional_polished: 'Professional & Polished',
      enthusiastic_energetic: 'Enthusiastic & Energetic',
      warm_nurturing: 'Warm & Nurturing',
      straightforward_efficient: 'Straightforward & Efficient',
    };
    return tones[value] || value;
  }
  // Truncate long values
  if (value && value.length > 100) {
    return value.substring(0, 100) + '...';
  }
  return value || '-';
}
