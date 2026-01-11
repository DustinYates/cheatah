/**
 * Transform lead data and conversation data into a unified chronological timeline
 * for display in the lead details modal.
 */

/**
 * Determine if a message is from SMS or web chatbot based on channel
 * @param {object} message - The message object
 * @param {string} channel - The conversation channel ('sms', 'text', 'web', 'web_chat', etc.)
 * @returns {boolean} - True if SMS, false if chatbot
 */
function determineIfSMS(message, channel) {
  if (!channel) return false;

  const channelLower = channel.toLowerCase();
  return channelLower === 'sms' || channelLower === 'text';
}

/**
 * Generate a concise summary for a voice call
 * @param {object} call - Voice call data from extra_data.voice_calls
 * @returns {string} - Brief summary line
 */
function generateCallSummary(call) {
  const name = call.caller_name || 'Unknown caller';
  const intent = call.caller_intent ? ` - ${call.caller_intent}` : '';
  return `Phone call from ${name}${intent}`;
}

/**
 * Generate a concise summary for a message (SMS or chatbot)
 * @param {object} msg - Message object
 * @returns {string} - Brief preview of message content
 */
function generateMessageSummary(msg) {
  const prefix = msg.role === 'user' ? 'User' : 'Bot';
  const content = msg.content || '';
  const preview = content.substring(0, 60);
  const ellipsis = content.length > 60 ? '...' : '';

  return `${prefix}: ${preview}${ellipsis}`;
}

/**
 * Build a unified timeline from lead data and conversation data
 * Groups consecutive conversation messages into single timeline items
 * @param {object} lead - Lead object with extra_data containing voice_calls
 * @param {object} conversationData - Conversation data with messages array
 * @returns {array} - Unified timeline sorted by timestamp (most recent first)
 */
export function buildUnifiedTimeline(lead, conversationData) {
  const timeline = [];

  // 1. Transform voice calls from lead.extra_data
  if (lead.extra_data?.voice_calls?.length > 0) {
    lead.extra_data.voice_calls.forEach((call, idx) => {
      // Handle various date formats
      let callDate = call.call_date;
      if (!callDate) {
        console.warn('Voice call missing call_date:', call);
        return; // Skip calls without dates
      }

      // If call_date is just a date string like "2026-01-10 14:30", add timezone
      if (callDate && !callDate.includes('T') && !callDate.includes('Z')) {
        callDate = callDate.replace(' ', 'T') + 'Z';
      }

      timeline.push({
        id: `voice-${call.call_id || idx}`,
        type: 'voice_call',
        timestamp: new Date(callDate),
        timestampISO: callDate,
        summary: generateCallSummary(call),
        icon: 'Phone',
        details: {
          caller_name: call.caller_name,
          caller_email: call.caller_email,
          caller_intent: call.caller_intent,
          full_summary: call.summary,
          transcript: call.transcript,
        }
      });
    });
  }

  // 2. Transform conversation messages (SMS + Chatbot) - GROUP them together
  if (conversationData?.messages?.length > 0) {
    const channel = conversationData.channel || 'web';
    const isSMS = determineIfSMS(conversationData.messages[0], channel);

    // Group all messages from the same conversation together
    const messages = conversationData.messages
      .filter(msg => msg.created_at) // Skip messages without timestamps
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at)); // Sort oldest first for display

    if (messages.length > 0) {
      // Use the timestamp of the most recent message
      const lastMessage = messages[messages.length - 1];

      timeline.push({
        id: `conversation-${conversationData.id || 'group'}`,
        type: isSMS ? 'sms' : 'chatbot',
        timestamp: new Date(lastMessage.created_at),
        timestampISO: lastMessage.created_at,
        summary: `Conversation (${messages.length} message${messages.length > 1 ? 's' : ''})`,
        icon: isSMS ? 'MessageSquare' : 'Bot',
        details: {
          messages: messages.map(msg => ({
            role: msg.role,
            content: msg.content,
            created_at: msg.created_at,
          })),
          channel: channel,
        }
      });
    }
  }

  // 3. Sort chronologically (most recent first)
  timeline.sort((a, b) => b.timestamp - a.timestamp);

  return timeline;
}

/**
 * Determine which source types are present in the timeline
 * Used for displaying source badges in the summary section
 * @param {array} timeline - Unified timeline array
 * @returns {object} - Object with boolean flags for each source type
 */
export function getTimelineSources(timeline) {
  const sources = {
    hasVoiceCalls: false,
    hasSMS: false,
    hasChatbot: false,
  };

  timeline.forEach(item => {
    if (item.type === 'voice_call') sources.hasVoiceCalls = true;
    if (item.type === 'sms') sources.hasSMS = true;
    if (item.type === 'chatbot') sources.hasChatbot = true;
  });

  return sources;
}
