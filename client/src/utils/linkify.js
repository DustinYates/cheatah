/**
 * URL Linkifier - Detects URLs in text and makes them clickable
 *
 * This utility:
 * 1. Detects URLs in text content
 * 2. Sanitizes URLs by removing whitespace (fixes broken URLs from LLM output)
 * 3. Returns React elements with clickable links
 */

/**
 * Sanitize a URL by removing any embedded whitespace
 * This fixes URLs that may have been corrupted by line breaks or spaces
 *
 * @param {string} url - The URL to sanitize
 * @returns {string} - Sanitized URL with no whitespace
 */
function sanitizeUrl(url) {
  // Remove any whitespace characters (spaces, newlines, tabs, etc.)
  return url.replace(/\s+/g, '');
}

/**
 * Check if a URL is a valid registration link
 * @param {string} url - The URL to check
 * @returns {boolean}
 */
function isValidRegistrationUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.hostname === 'britishswimschool.com' &&
           parsed.pathname.includes('/register');
  } catch {
    return false;
  }
}

/**
 * Linkify text content - converts URLs to clickable links
 *
 * @param {string} text - The text content that may contain URLs
 * @returns {Array} - Array of React elements (strings and anchor elements)
 */
export function linkifyText(text) {
  if (!text || typeof text !== 'string') {
    return text;
  }

  // URL pattern - matches http/https URLs
  // This pattern is designed to capture full URLs including query strings
  const urlPattern = /(https?:\/\/[^\s<>"']+)/gi;

  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = urlPattern.exec(text)) !== null) {
    // Add text before the URL
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }

    // Sanitize and add the URL as a link
    let url = match[1];

    // Remove trailing punctuation that's not part of the URL
    let trailing = '';
    while (url.length > 0 && /[.,;:!?)}\]>]$/.test(url)) {
      // Keep trailing ) only if there's a matching ( in the URL
      if (url.endsWith(')') && url.includes('(')) {
        break;
      }
      trailing = url.slice(-1) + trailing;
      url = url.slice(0, -1);
    }

    // Sanitize the URL (remove any embedded whitespace)
    const sanitizedUrl = sanitizeUrl(url);

    // Create the link element
    parts.push({
      type: 'link',
      url: sanitizedUrl,
      key: `link-${match.index}`
    });

    // Add back any trailing punctuation
    if (trailing) {
      parts.push(trailing);
    }

    lastIndex = match.index + match[0].length;
  }

  // Add any remaining text
  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }

  return parts.length > 0 ? parts : [text];
}

/**
 * Render linkified content as React elements
 *
 * @param {string} text - The text content to linkify
 * @param {Object} options - Options for rendering
 * @param {string} options.linkClassName - CSS class for links
 * @returns {Array<React.ReactNode>} - Array of React elements
 */
export function renderLinkifiedText(text, options = {}) {
  const { linkClassName = 'message-link' } = options;
  const parts = linkifyText(text);

  if (!Array.isArray(parts)) {
    return text;
  }

  return parts.map((part, index) => {
    if (typeof part === 'string') {
      return part;
    }
    if (part.type === 'link') {
      return (
        <a
          key={part.key || index}
          href={part.url}
          target="_blank"
          rel="noopener noreferrer"
          className={linkClassName}
        >
          {part.url}
        </a>
      );
    }
    return part;
  });
}

export default { linkifyText, renderLinkifiedText };
