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
 * Join URLs that were split across multiple lines by LLM output
 * e.g., "https://britishswimschool\n.com/path" -> "https://britishswimschool.com/path"
 *
 * @param {string} text - The text that may contain split URLs
 * @returns {string} - Text with URLs joined
 */
function joinSplitUrls(text) {
  let result = text;
  let iterations = 0;
  const maxIterations = 15; // Safety limit - may need multiple passes

  while (iterations < maxIterations) {
    const before = result;

    // Match: URL + whitespace + any non-whitespace chunk
    result = result.replace(
      /(https?:\/\/[^\s<>"']+)(\s+)(\S+)/gi,
      (match, urlPart, whitespace, continuation) => {
        // Always join if continuation contains URL-indicative characters
        // (dots, slashes, query params, percent-encoding, equals, ampersands)
        if (/[./\\?&=%]/.test(continuation)) {
          return urlPart + continuation;
        }

        // Join path segments that follow an incomplete URL path
        // e.g., "https://site.com/cy" + "press-spring" should join
        if (/^[a-z0-9][a-z0-9-_]*$/i.test(continuation)) {
          // Check if URL ends with a partial path (ends with /word or just domain)
          if (/\/[a-z0-9-_]*$/i.test(urlPart)) {
            return urlPart + continuation;
          }
        }

        return match; // Don't join - probably regular text
      }
    );

    if (result === before) break;
    iterations++;
  }
  return result;
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

  // First, join any URLs that were split across lines
  const textWithJoinedUrls = joinSplitUrls(text);

  // URL pattern - matches http/https URLs
  // This pattern is designed to capture full URLs including query strings
  const urlPattern = /(https?:\/\/[^\s<>"']+)/gi;

  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = urlPattern.exec(textWithJoinedUrls)) !== null) {
    // Add text before the URL
    if (match.index > lastIndex) {
      parts.push(textWithJoinedUrls.substring(lastIndex, match.index));
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
  if (lastIndex < textWithJoinedUrls.length) {
    parts.push(textWithJoinedUrls.substring(lastIndex));
  }

  return parts.length > 0 ? parts : [textWithJoinedUrls];
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
