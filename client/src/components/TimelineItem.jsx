import { Phone, MessageSquare, Bot, Mail, ChevronDown } from 'lucide-react';
import { formatSmartDateTime } from '../utils/dateFormat';

/**
 * Get the appropriate icon component based on type
 */
function getIconComponent(iconName) {
  const icons = {
    Phone: Phone,
    MessageSquare: MessageSquare,
    Bot: Bot,
    Mail: Mail,
  };
  return icons[iconName] || Phone;
}

/**
 * Render type-specific detail view for voice calls
 */
function VoiceCallDetails({ details }) {
  return (
    <div className="timeline-details-content">
      {details.full_summary && (
        <div className="detail-section">
          <span className="detail-label">Summary</span>
          <p className="detail-value">{details.full_summary}</p>
        </div>
      )}

      {details.transcript && (
        <div className="detail-section">
          <span className="detail-label">Transcript</span>
          <p className="detail-value detail-transcript">{details.transcript}</p>
        </div>
      )}

      {(details.caller_name || details.caller_email || details.caller_intent) && (
        <div className="detail-section">
          <span className="detail-label">Details</span>
          <div className="detail-metadata">
            {details.caller_name && (
              <div className="metadata-item">
                <span className="metadata-item-label">Name:</span>
                <span className="metadata-item-value">{details.caller_name}</span>
              </div>
            )}
            {details.caller_email && (
              <div className="metadata-item">
                <span className="metadata-item-label">Email:</span>
                <span className="metadata-item-value">{details.caller_email}</span>
              </div>
            )}
            {details.caller_intent && (
              <div className="metadata-item">
                <span className="metadata-item-label">Intent:</span>
                <span className="metadata-item-value">{details.caller_intent}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Render type-specific detail view for SMS and chatbot messages
 * Now handles grouped conversation messages
 */
function MessageDetails({ details }) {
  // Check if this is a grouped conversation (multiple messages)
  if (details.messages && Array.isArray(details.messages)) {
    return (
      <div className="timeline-details-content">
        <div className="detail-section">
          <div className="conversation-messages">
            {details.messages.map((msg, idx) => (
              <div key={idx} className={`conversation-message ${msg.role}`}>
                <div className="conversation-message-role">
                  {msg.role === 'user' ? 'User' : 'Bot'}
                </div>
                <div className="conversation-message-content">{msg.content}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Fallback for single message (shouldn't happen with new grouping)
  return (
    <div className="timeline-details-content">
      <div className="detail-section">
        <span className="detail-label">Full Message</span>
        <p className="detail-value detail-message">{details.content}</p>
      </div>

      <div className="detail-metadata">
        <div className="metadata-item">
          <span className="metadata-item-label">From:</span>
          <span className="metadata-item-value">{details.role === 'user' ? 'Customer' : 'Bot'}</span>
        </div>
        <div className="metadata-item">
          <span className="metadata-item-label">Channel:</span>
          <span className="metadata-item-value">{details.channel}</span>
        </div>
      </div>
    </div>
  );
}

/**
 * Render details based on timeline item type
 */
function renderDetailsForType(item) {
  switch (item.type) {
    case 'voice_call':
      return <VoiceCallDetails details={item.details} />;
    case 'sms':
    case 'chatbot':
      return <MessageDetails details={item.details} />;
    default:
      return null;
  }
}

/**
 * TimelineItem Component
 * Represents a single interaction in the timeline (voice call, SMS, or chatbot message)
 * Supports expand/collapse functionality with smooth animation
 */
export default function TimelineItem({ item, isExpanded, onToggle, isLast }) {
  const Icon = getIconComponent(item.icon);

  return (
    <div className="timeline-item">
      {/* Vertical connector line */}
      {!isLast && <div className="timeline-item-line" />}

      {/* Icon circle */}
      <div className={`timeline-item-icon timeline-item-icon--${item.type}`}>
        <Icon size={18} strokeWidth={2} />
      </div>

      {/* Content card */}
      <div className="timeline-item-content">
        {/* Always-visible header (clickable) */}
        <button
          className="timeline-item-header"
          onClick={onToggle}
          aria-expanded={isExpanded}
          type="button"
        >
          <span className="timeline-item-summary">{item.summary}</span>
          <div className="timeline-item-header-right">
            <span className="timeline-item-timestamp">
              {formatSmartDateTime(item.timestampISO)}
            </span>
            <ChevronDown
              size={16}
              className={`timeline-item-chevron ${isExpanded ? 'expanded' : ''}`}
            />
          </div>
        </button>

        {/* Expandable details section */}
        <div className={`timeline-item-details ${isExpanded ? 'expanded' : ''}`}>
          <div className="timeline-item-details-inner">
            {renderDetailsForType(item)}
          </div>
        </div>
      </div>
    </div>
  );
}
