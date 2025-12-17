"""Gemini client implementation using Replit AI Integrations."""

import os
from typing import Any

from google import genai
from google.genai import types

from app.llm.client import LLMClient
from app.settings import settings


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
            generation_config: dict[str, Any] = {
                "temperature": 0.3,
                "max_output_tokens": 500,
            }
            
            if context:
                if "temperature" in context:
                    generation_config["temperature"] = context["temperature"]
                if "max_tokens" in context:
                    generation_config["max_output_tokens"] = context["max_tokens"]
            
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(**generation_config),
            )
            
            return response.text or ""
        except Exception as e:
            raise Exception(f"Gemini generation failed: {str(e)}") from e

