// Helpers for the manual drip-campaign enroll action.
//
// The backend (lead_tagger.infer_audience + detect_campaign_type) is the
// authoritative source of truth for kids vs adults. These helpers only derive
// what to SHOW in the confirm dialog and what type to send so the confirmed
// choice matches what gets enrolled. Returns null when undeterminable — the
// backend then auto-detects and the confirm text falls back to a generic label.

/**
 * Derive the drip campaign type ('adults' | 'kids' | null) from a lead's
 * audience tag (category: 'audience', value e.g. "Adult" / "Child (under 3)"),
 * falling back to its manual custom_tags.
 */
export function getLeadDripCampaignType(lead) {
  const tags = Array.isArray(lead?.tags) ? lead.tags : [];
  const audience = tags.find((t) => t?.category === 'audience')?.value;
  if (audience) {
    return /adult/i.test(audience) ? 'adults' : 'kids';
  }

  const custom = Array.isArray(lead?.custom_tags) ? lead.custom_tags.join(' ') : '';
  if (/adult/i.test(custom)) return 'adults';
  if (/child|kid|under 3/i.test(custom)) return 'kids';

  return null;
}

/** Human label for a campaign type ('' when undeterminable), for confirm dialogs / toasts. */
export function dripCampaignTypeLabel(type) {
  if (type === 'adults') return 'Adults';
  if (type === 'kids') return 'Kids';
  return '';
}

/** Phrase like "the Kids drip campaign" / "the drip campaign" for confirm text. */
export function dripCampaignPhrase(type) {
  const label = dripCampaignTypeLabel(type);
  return `the ${label ? `${label} ` : ''}drip campaign`;
}
