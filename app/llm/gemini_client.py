"""Gemini client implementation using Replit AI Integrations."""

import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types

from app.llm.client import LLMClient
from app.settings import settings

logger = logging.getLogger(__name__)


class GeminiClient(LLMClient):
    """Gemini client using Replit AI Integrations."""

    def __init__(self) -> None:
        """Initialize Gemini client with Replit AI Integrations."""
        api_key = os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY", settings.gemini_api_key)
        base_url = os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL")
        
        if base_url:
            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(api_version="v1beta", base_url=base_url),
            )
        else:
            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(api_version="v1beta"),
            )
        self.model_name = settings.gemini_model

    def _build_generation_config(self, context: dict | None = None) -> dict[str, Any]:
        """Build generation config from context.
        
        Args:
            context: Optional context dictionary with temperature, max_tokens, etc.
            
        Returns:
            Generation config dictionary
        """
        generation_config: dict[str, Any] = {
            "temperature": 0.3,
            "max_output_tokens": 1500,
        }
        
        if context:
            if "temperature" in context:
                generation_config["temperature"] = context["temperature"]
            if "max_tokens" in context:
                generation_config["max_output_tokens"] = context["max_tokens"]
        
        return generation_config

    async def generate(self, prompt: str, context: dict | None = None) -> str:
        """Generate a response using Gemini.

        Args:
            prompt: The prompt to send to the LLM
            context: Optional context dictionary (temperature, max_tokens, etc.)

        Returns:
            The generated response text

        Raises:
            Exception: If generation fails
        """
        try:
            generation_config = self._build_generation_config(context)
            
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(**generation_config),
            )

            # Check for empty response and log the reason
            if not response.text:
                # Log why response might be empty (safety filtering, recitation block, etc.)
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    finish_reason = getattr(candidate, 'finish_reason', 'UNKNOWN')
                    logger.warning(f"Gemini returned empty text - finish_reason: {finish_reason}")
                    if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                        ratings = [(r.category, r.probability) for r in candidate.safety_ratings]
                        logger.warning(f"Safety ratings: {ratings}")
                if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                    logger.warning(f"Prompt feedback: {response.prompt_feedback}")

            return response.text or ""
        except Exception as e:
            raise Exception(f"Gemini generation failed: {str(e)}") from e

    async def generate_stream(
        self, prompt: str, context: dict | None = None
    ) -> AsyncIterator[str]:
        """Generate a streaming response using Gemini.
        
        Yields tokens as they are generated for lower perceived latency.
        This is critical for voice applications where we want to start
        speaking as soon as the first clause is complete.
        
        Args:
            prompt: The prompt to send to the LLM
            context: Optional context dictionary (temperature, max_tokens, etc.)
            
        Yields:
            Chunks of generated text as they become available
            
        Raises:
            Exception: If streaming generation fails
        """
        try:
            generation_config = self._build_generation_config(context)
            start_time = time.time()
            first_token_time = None
            
            # Use async streaming API
            async for chunk in self.client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(**generation_config),
            ):
                if chunk.text:
                    if first_token_time is None:
                        first_token_time = time.time()
                        ttft = (first_token_time - start_time) * 1000
                        logger.info(f"Gemini streaming TTFT: {ttft:.1f}ms")
                    
                    yield chunk.text
            
            total_time = (time.time() - start_time) * 1000
            logger.info(f"Gemini streaming total: {total_time:.1f}ms")
            
        except Exception as e:
            logger.error(f"Gemini streaming failed: {e}", exc_info=True)
            raise Exception(f"Gemini streaming failed: {str(e)}") from e

