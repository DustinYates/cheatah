"""Gemini Flash 2.5 client implementation."""

import asyncio
from typing import Any

import google.generativeai as genai

from app.llm.client import LLMClient
from app.settings import settings


class GeminiClient(LLMClient):
    """Gemini Flash 2.5 client implementation."""

    def __init__(self) -> None:
        """Initialize Gemini client."""
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(settings.gemini_model)

    async def generate(self, prompt: str, context: dict | None = None) -> str:
        """Generate a response using Gemini Flash 2.5.

        Args:
            prompt: The prompt to send to the LLM
            context: Optional context dictionary (temperature, max_tokens, etc.)

        Returns:
            The generated response text

        Raises:
            Exception: If generation fails
        """
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            generation_config: dict[str, Any] = {}
            
            # Default to deterministic settings (low temperature)
            generation_config["temperature"] = 0.3
            generation_config["max_output_tokens"] = 500
            
            if context:
                if "temperature" in context:
                    generation_config["temperature"] = context["temperature"]
                if "max_tokens" in context:
                    generation_config["max_output_tokens"] = context["max_tokens"]
            
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(**generation_config) if generation_config else None
                )
            )
            
            return response.text
        except Exception as e:
            # Log error and re-raise
            raise Exception(f"Gemini generation failed: {str(e)}") from e

