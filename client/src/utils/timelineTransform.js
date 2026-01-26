/**
 * Transform lead data and conversation data into a unified chronological timeline
 * for display in the lead details modal.
 */

/**
 * Determine the channel type based on channel string
 * @param {string} channel - The conversation channel ('sms', 'text', 'web', 'web_chat', 'email', 'form', etc.)
 * @returns {string} - Channel type: 'sms', 'email', or 'chatbot'
 */
function determineChannelType(channel) {
  if (!channel) return 'chatbot';

  const channelLower = channel.toLowerCase();

  // SMS channels
  if (channelLower === 'sms' || channelLower === 'text') {
    return 'sms';
  }

  // Email/form channels
  if (channelLower === 'email' || channelLower === 'form' || channelLower === 'web_form' || channelLower === 'contact_form') {
    return 'email';
  }

  // Default to chatbot for web chat
  return 'chatbot';
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
  const seenCallIds = new Set();

  // 1. Transform voice calls from lead.extra_data - with deduplication
  if (lead.extra_data?.voice_calls?.length > 0) {
    lead.extra_data.voice_calls.forEach((call, idx) => {
      // Handle various date formats
      let callDate = call.call_date;
      if (!callDate) {
        console.warn('Voice call missing call_date:', call);
        return; // Skip calls without dates
      }

      // Deduplicate by call_id if available
      if (call.call_id) {
        if (seenCallIds.has(call.call_id)) {
          return; // Skip duplicate
        }
        seenCallIds.add(call.call_id);
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

  // 2. Transform conversation messages (SMS + Chatbot + Email/Form) - GROUP them together
  // Handle both single conversation (legacy) and multiple conversations (new format)
  const conversations = conversationData?.conversations || (conversationData?.messages ? [conversationData] : []);

  conversations.forEach(conv => {
    if (!conv?.messages?.length) return;

    const channel = conv.channel || 'web';
    const channelType = determineChannelType(channel);

    // Map channel type to timeline type and icon
    const typeMap = {
      sms: { type: 'sms', icon: 'MessageSquare' },
      email: { type: 'email', icon: 'Mail' },
      chatbot: { type: 'chatbot', icon: 'Bot' },
    };
    const { type: itemType, icon: itemIcon } = typeMap[channelType] || typeMap.chatbot;

    // Group all messages from the same conversation together
    const messages = conv.messages
      .filter(msg => msg.created_at) // Skip messages without timestamps
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at)); // Sort oldest first for display

    if (messages.length > 0) {
      // Use the timestamp of the most recent message
      const lastMessage = messages[messages.length - 1];

      // Generate appropriate summary based on channel type
      let summary = `Conversation (${messages.length} message${messages.length > 1 ? 's' : ''})`;
      if (channelType === 'email') {
        summary = `Get In Touch Form Submission`;
      }

      timeline.push({
        id: `conversation-${conv.id || 'group'}`,
        type: itemType,
        timestamp: new Date(lastMessage.created_at),
        timestampISO: lastMessage.created_at,
        summary: summary,
        icon: itemIcon,
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
  });

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
    hasEmail: false,
  };

  timeline.forEach(item => {
    if (item.type === 'voice_call') sources.hasVoiceCalls = true;
    if (item.type === 'sms') sources.hasSMS = true;
    if (item.type === 'chatbot') sources.hasChatbot = true;
    if (item.type === 'email') sources.hasEmail = true;
  });

  return sources;
}
