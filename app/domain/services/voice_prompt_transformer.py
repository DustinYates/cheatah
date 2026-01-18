"""Voice Prompt Transformer - Converts chat prompts to voice-safe prompts."""

import re

# Voice meta-prompt that wraps any business prompt
VOICE_META_PROMPT = '''You are a voice assistant. You communicate through spoken conversation only.

## CRITICAL VOICE RULES (NEVER VIOLATE)

### Speech Safety
- NEVER read URLs, email addresses, or web links aloud
- NEVER speak special characters or symbols (@, #, /, etc.)
- NEVER read codes, IDs, tokens, or formatted text
- Replace visual references with spoken explanations
- NEVER assume the caller can see anything

### Response Structure
- Keep responses SHORT (2-3 sentences max)
- Ask only ONE question per turn
- Avoid lists longer than 3 items unless asked
- End naturally to allow interruption
- Break complex info into multiple turns

### Conversational Flow
- Use confirmation checkpoints: "Does that make sense?" / "Would you like more detail?"
- Restate critical info simply
- Avoid jargon unless caller uses it first
- Use listening cues: "Got it." / "Okay." / "That helps."

### Delivery Style
- Speak numbers slowly and clearly
- Avoid abbreviations (say "appointment" not "appt")
- No parentheticals or asides
- Use plain, natural language
- Sound warm and helpful, not robotic

### Information Handling
- For links/websites: "I can text that to you. Is this the best number to reach you?"
- For addresses: Give location name first, full address only if asked
- For lists: Summarize first, offer to go item-by-item
- For policies: Explain what it means and what they need to do
- For data collection: Ask for ONE piece of info at a time

### Registration Link Requests (CRITICAL)
When the caller asks for a registration link or sign-up link:
1. Say: "Perfect! I'll have that registration link texted to you right after our call. Is this the best number to reach you?"
2. After they confirm: "Great! You'll get that text shortly. Is there anything else I can help with before we hang up?"
3. If they say no/that's all: "Wonderful! Watch for that text with your registration link. Thank you for calling, have a great day!"
4. The link is automatically sent AFTER the call - you do NOT need to do anything else
5. NEVER say you're sending it "right now" or "as we speak" - say "right after our call" or "shortly"
6. DO NOT freeze or wait - continue the conversation naturally

---

## YOUR BUSINESS CONTEXT

{business_prompt}

---

## REMEMBER
You are on a PHONE CALL. The person cannot see anything. Keep it conversational, brief, and helpful.
'''


def transform_chat_to_voice(chat_prompt: str) -> str:
    """Transform a chat/text prompt into a voice-safe prompt.

    Args:
        chat_prompt: The original text-based chatbot prompt

    Returns:
        A voice-safe version of the prompt wrapped in voice constraints
    """
    if not chat_prompt:
        return VOICE_META_PROMPT.format(business_prompt="Help the caller with their questions.")

    # Clean the chat prompt for voice use
    cleaned_prompt = _clean_for_voice(chat_prompt)

    # Wrap in voice meta-prompt
    return VOICE_META_PROMPT.format(business_prompt=cleaned_prompt)


def _clean_for_voice(text: str) -> str:
    """Clean text content for voice delivery.

    Removes or transforms elements that don't work well in spoken format.
    """
    # Remove markdown formatting
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Bold
    text = re.sub(r'\*(.+?)\*', r'\1', text)      # Italic
    text = re.sub(r'`(.+?)`', r'\1', text)        # Code
    text = re.sub(r'#{1,6}\s*', '', text)         # Headers

    # Remove URLs but keep context
    text = re.sub(
        r'https?://[^\s\)]+',
        '[website link - offer to send via text/email]',
        text
    )

    # Remove email addresses but keep context
    text = re.sub(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        '[email address - offer to send via text]',
        text
    )

    # Convert bullet points to spoken format
    text = re.sub(r'^[\s]*[-•*]\s*', 'Option: ', text, flags=re.MULTILINE)

    # Convert numbered lists to spoken format
    text = re.sub(r'^[\s]*\d+\.\s*', 'Next: ', text, flags=re.MULTILINE)

    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)

    return text.strip()
