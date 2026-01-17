"""Factory to create LLM clients based on a mode string or env var."""
import os
from typing import Optional

from app.llm.client import LLMClient
from app.llm.gemini_client import GeminiClient


def get_llm_client(mode: Optional[str] = None) -> LLMClient:
    """Return an LLMClient instance for the requested mode.

    Priority: explicit `mode` argument -> `LLM_MODE` env var -> default 'gemini'
    """
    selected = (mode or os.environ.get("LLM_MODE") or "gemini").lower()

    if selected in ("gemini", "google", "googleai"):
        return GeminiClient()

    # Future providers can be added here (openai, anthropic, etc.)
    raise ValueError(f"Unsupported LLM mode: {selected}")
