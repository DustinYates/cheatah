"""LLM orchestrator stub for future tool/function calling."""

from collections.abc import AsyncIterator

from app.llm.client import LLMClient
from app.llm.factory import get_llm_client


class LLMOrchestrator:
    """Orchestrator for LLM interactions (stub for future tool logic)."""

    def __init__(self, client: LLMClient | None = None, mode: str | None = None) -> None:
        """Initialize orchestrator with LLM client or a mode string.

        Provide either a concrete `client` instance or a `mode` (eg. 'gemini').
        If neither is provided, the factory selects a default (gemini).
        """
        if client is not None:
            self.client = client
        else:
            self.client = get_llm_client(mode)

    async def generate(self, prompt: str, context: dict | None = None) -> str:
        """Generate response using the LLM client.

        Currently just passes through to client.
        Future: Will handle tool/function calling, multi-step reasoning, etc.

        Args:
            prompt: The prompt to send
            context: Optional context dictionary

        Returns:
            The generated response
        """
        return await self.client.generate(prompt, context)

    async def generate_stream(
        self, prompt: str, context: dict | None = None
    ) -> AsyncIterator[str]:
        """Generate streaming response using the LLM client.
        
        Yields tokens as they are generated for lower perceived latency.
        Critical for voice applications where we want to start speaking
        as soon as the first clause is complete.
        
        Args:
            prompt: The prompt to send
            context: Optional context dictionary
            
        Yields:
            Chunks of generated text as they become available
        """
        async for chunk in self.client.generate_stream(prompt, context):
            yield chunk

