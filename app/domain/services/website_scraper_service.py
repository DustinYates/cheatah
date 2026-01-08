"""Service for scraping business websites and extracting structured data."""

import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, quote

import httpx

from app.settings import settings
from app.domain.models.scraped_data import (
    BusinessHours,
    FAQPair,
    LocationInfo,
    PolicyInfo,
    PricingInfo,
    ProgramInfo,
    ScrapedBusinessData,
    ServiceInfo,
)
from app.llm.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

# Common subpages to check for additional content
COMMON_SUBPAGES = [
    "/about",
    "/about-us",
    "/services",
    "/programs",
    "/classes",
    "/pricing",
    "/prices",
    "/rates",
    "/faq",
    "/faqs",
    "/contact",
    "/contact-us",
    "/locations",
    "/hours",
    "/policies",
    "/our-locations",
    "/our-programs",
]

# Browser-like user agent to avoid bot detection
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Common browser headers (no Accept-Encoding to avoid compressed responses)
BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
}

# Extraction prompt for the LLM
EXTRACTION_PROMPT = """You are a business information extraction assistant. Given website content, extract structured business data.

Extract the following information from the website content below. Return ONLY valid JSON with no additional text.

Required JSON structure:
{{
    "business_name": "string or null",
    "business_description": "string or null",
    "locations": [
        {{
            "name": "string or null",
            "address": "string or null",
            "city": "string or null",
            "state": "string or null",
            "zip_code": "string or null",
            "phone": "string or null",
            "email": "string or null"
        }}
    ],
    "hours": [
        {{
            "day": "string (monday, tuesday, etc.)",
            "location_name": "string or null if same for all",
            "open_time": "HH:MM format",
            "close_time": "HH:MM format",
            "notes": "string or null"
        }}
    ],
    "services": [
        {{
            "name": "string",
            "description": "string or null",
            "price": "string or null",
            "url": "string or null"
        }}
    ],
    "programs": [
        {{
            "name": "string",
            "description": "string or null",
            "age_range": "string or null",
            "skill_level": "string or null",
            "prerequisites": "string or null",
            "max_class_size": "number or null",
            "duration": "string or null",
            "registration_url": "string or null"
        }}
    ],
    "pricing": [
        {{
            "item": "string",
            "price": "string or null",
            "frequency": "string (per lesson, monthly, etc.) or null",
            "notes": "string or null"
        }}
    ],
    "faqs": [
        {{
            "question": "string",
            "answer": "string"
        }}
    ],
    "policies": [
        {{
            "policy_type": "string (cancellation, refund, makeup, booking, etc.)",
            "description": "string",
            "details": ["string"] or null
        }}
    ],
    "unique_selling_points": ["string"],
    "target_audience": "string or null (e.g., 'Children ages 3 months to adults')"
}}

Important:
- Extract all relevant information you can find
- If information is not available, use null or empty arrays
- For hours, use 24-hour format (e.g., "09:00", "17:00")
- Include any pricing tiers or packages found
- Capture FAQ content if present
- Look for policies like cancellation, refund, makeup class policies
- Identify the target demographic/audience

Website content to analyze:

{content}

Return ONLY the JSON object, no additional text or markdown."""


class WebsiteScraperService:
    """Service for scraping business websites and extracting structured data using LLM."""

    def __init__(self) -> None:
        """Initialize the scraper service."""
        self.llm_client = GeminiClient()
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    async def scrape_business_website(self, url: str) -> ScrapedBusinessData:
        """Scrape a business website and extract structured data.

        Args:
            url: The business website URL to scrape

        Returns:
            ScrapedBusinessData object with extracted information
        """
        logger.info(f"Starting website scrape for: {url}")

        # Normalize URL
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        pages_scraped = []
        all_content = []

        # Fetch main page
        main_content = await self._fetch_page(url)
        if main_content:
            all_content.append(f"=== MAIN PAGE ({url}) ===\n{main_content}")
            pages_scraped.append(url)

        # Fetch common subpages
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        path = urlparse(url).path.rstrip("/")

        for subpage in COMMON_SUBPAGES:
            # Try both with and without the base path
            subpage_urls = [
                urljoin(url, subpage),
                f"{base_url}{subpage}",
            ]
            if path:
                subpage_urls.append(f"{base_url}{path}{subpage}")

            for subpage_url in subpage_urls:
                if subpage_url not in pages_scraped:
                    content = await self._fetch_page(subpage_url)
                    if content and len(content) > 200:  # Only include if meaningful content
                        all_content.append(f"=== {subpage.upper()} PAGE ({subpage_url}) ===\n{content}")
                        pages_scraped.append(subpage_url)
                        break  # Found this subpage, move to next

        if not all_content:
            logger.warning(f"Could not fetch any content from {url}")
            return ScrapedBusinessData(
                scraped_at=datetime.utcnow(),
                source_url=url,
                pages_scraped=[],
            )

        # Combine all content and extract structured data
        combined_content = "\n\n".join(all_content)

        # Truncate if too long (LLM context limit)
        max_content_length = 50000
        if len(combined_content) > max_content_length:
            combined_content = combined_content[:max_content_length] + "\n\n[Content truncated...]"

        # Extract structured data using LLM
        extracted_data = await self._extract_with_llm(combined_content)

        # Build the result
        result = ScrapedBusinessData(
            business_name=extracted_data.get("business_name"),
            business_description=extracted_data.get("business_description"),
            locations=[LocationInfo(**loc) for loc in extracted_data.get("locations", []) if loc],
            hours=[BusinessHours(**h) for h in extracted_data.get("hours", []) if h],
            services=[ServiceInfo(**s) for s in extracted_data.get("services", []) if s],
            programs=[ProgramInfo(**p) for p in extracted_data.get("programs", []) if p],
            pricing=[PricingInfo(**p) for p in extracted_data.get("pricing", []) if p],
            faqs=[FAQPair(**f) for f in extracted_data.get("faqs", []) if f],
            policies=[PolicyInfo(**p) for p in extracted_data.get("policies", []) if p],
            unique_selling_points=extracted_data.get("unique_selling_points", []),
            target_audience=extracted_data.get("target_audience"),
            raw_content=combined_content[:10000],  # Store truncated raw content
            scraped_at=datetime.utcnow(),
            source_url=url,
            pages_scraped=pages_scraped,
        )

        logger.info(
            f"Scraped {url}: {len(result.services)} services, "
            f"{len(result.programs)} programs, {len(result.faqs)} FAQs, "
            f"{len(result.locations)} locations"
        )

        return result

    async def _fetch_page(self, url: str, use_scrapingbee_fallback: bool = True) -> str | None:
        """Fetch a single page and return cleaned text content.

        Args:
            url: The URL to fetch
            use_scrapingbee_fallback: Whether to try ScrapingBee if direct fetch fails

        Returns:
            Cleaned text content or None if fetch failed
        """
        # Try direct fetch first
        content = await self._fetch_page_direct(url)

        # If direct fetch failed and we have ScrapingBee configured, try it as fallback
        if content is None and use_scrapingbee_fallback and settings.scrapingbee_api_key:
            logger.info(f"Direct fetch failed for {url}, trying ScrapingBee fallback")
            content = await self._fetch_page_scrapingbee(url)

        return content

    async def _fetch_page_direct(self, url: str) -> str | None:
        """Fetch a page directly using httpx.

        Args:
            url: The URL to fetch

        Returns:
            Cleaned text content or None if fetch failed
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=BROWSER_HEADERS)

                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    if "text/html" in content_type or "application/xhtml" in content_type:
                        html = response.text
                        return self._html_to_text(html)
                    else:
                        logger.debug(f"Skipping non-HTML content at {url}: {content_type}")
                        return None
                elif response.status_code == 403:
                    logger.info(f"HTTP 403 (blocked) for {url} - may need ScrapingBee")
                    return None
                else:
                    logger.debug(f"HTTP {response.status_code} for {url}")
                    return None

        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching {url}")
            return None
        except httpx.RequestError as e:
            logger.warning(f"Error fetching {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            return None

    async def _fetch_page_scrapingbee(self, url: str) -> str | None:
        """Fetch a page using ScrapingBee API (for sites with bot protection).

        Args:
            url: The URL to fetch

        Returns:
            Cleaned text content or None if fetch failed
        """
        if not settings.scrapingbee_api_key:
            logger.debug("ScrapingBee API key not configured")
            return None

        try:
            # ScrapingBee API endpoint
            scrapingbee_url = "https://app.scrapingbee.com/api/v1/"
            params = {
                "api_key": settings.scrapingbee_api_key,
                "url": url,
                "render_js": "false",  # Faster, no JS rendering needed for most sites
                "premium_proxy": "true",  # Use premium proxies to bypass Cloudflare
            }

            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                response = await client.get(scrapingbee_url, params=params)

                if response.status_code == 200:
                    html = response.text
                    logger.info(f"ScrapingBee successfully fetched {url}")
                    return self._html_to_text(html)
                else:
                    logger.warning(f"ScrapingBee returned {response.status_code} for {url}: {response.text[:200]}")
                    return None

        except httpx.TimeoutException:
            logger.warning(f"ScrapingBee timeout for {url}")
            return None
        except Exception as e:
            logger.error(f"ScrapingBee error for {url}: {e}")
            return None

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to readable text.

        Simple regex-based HTML to text conversion. For production,
        consider using beautifulsoup4 for better parsing.

        Args:
            html: Raw HTML content

        Returns:
            Cleaned text content
        """
        # Remove script and style elements
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML comments
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

        # Remove noscript
        text = re.sub(r"<noscript[^>]*>.*?</noscript>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Replace common block elements with newlines
        text = re.sub(r"<(br|p|div|h[1-6]|li|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)

        # Remove remaining HTML tags
        text = re.sub(r"<[^>]+>", " ", text)

        # Decode common HTML entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#39;", "'")
        text = text.replace("&apos;", "'")

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)

        return text.strip()

    async def _extract_with_llm(self, content: str) -> dict:
        """Extract structured data from content using LLM.

        Args:
            content: Text content to analyze

        Returns:
            Dictionary with extracted structured data
        """
        try:
            prompt = EXTRACTION_PROMPT.format(content=content)

            response = await self.llm_client.generate(
                prompt,
                context={"temperature": 0.1, "max_tokens": 4000},
            )

            # Try to parse JSON from response
            # Handle potential markdown code blocks
            response = response.strip()
            if response.startswith("```"):
                # Remove markdown code block
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                response = "\n".join(lines)

            # Try to find JSON object in response
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                response = json_match.group()

            data = json.loads(response)
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Response was: {response[:500]}...")
            return {}
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return {}
