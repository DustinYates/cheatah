
## Usage Instructions

1. Copy the entire text block between the triple backticks above
2. Navigate to the Telnyx portal for agent BSS_003 (`assistant-109f3350-874f-4770-87d4-737450280441`)
3. Paste into the System Prompt / Instructions field
4. Save and test

## Recent Changes

**2026-02-16**: Rewrote RESPONSE STYLE section and all scripted responses for conversational speech:
- Added explicit conversational speech directives (contractions, fragments, casual transitions)
- Included GOOD vs BAD example responses to anchor the LLM's tone
- Updated ~30 scripted/example lines throughout the prompt to use natural contractions and fragments
- Changed formal phrasings like "May I get your name?" → "Can I get your name?", "Would you prefer?" → "Which one's closer to you?"

**2026-02-16**: Added FILLER RESPONSES section to eliminate dead air during tool calls and processing:
- Filler phrases before tool calls ("Let me pull that up for you", "One sec, let me check on that")
- Acknowledgment phrases after caller provides info ("Got it", "Perfect")
- Rules: one filler per pause, vary phrases, keep under 8 words

**2026-02-08**: Added GLOBAL PRONUNCIATION rules to fix robotic voice and pronunciation issues:
- Never spell words letter-by-letter (fixes "makeups" → "make U P S" issue)
- English handling in Spanish context (natural pronunciation of English brand names)
- Initialisms & acronyms pronunciation rules
- Prosody & pacing guidelines

## Related Documentation

- [Telnyx Voice Agents](./TELNYX_VOICE_AGENTS.md) - Agent configuration details
- [Telnyx Webhook Setup](./TELNYX_WEBHOOK_SETUP.md) - Webhook URLs
