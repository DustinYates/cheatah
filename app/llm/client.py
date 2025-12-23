"""LLM client interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    async def generate(self, prompt: str, context: dict | None = None) -> str:
        """Generate a response from the LLM.

        Args:
            prompt: The prompt to send to the LLM
            context: Optional context dictionary for additional parameters

        Returns:
            The generated response text
        """
        pass

    async def generate_stream(
        self, prompt: str, context: dict | None = None
    ) -> AsyncIterator[str]:
        """Generate a streaming response from the LLM.
        
        Yields tokens as they are generated for lower perceived latency.
        Default implementation falls back to non-streaming generate().
        
        Args:
            prompt: The prompt to send to the LLM
            context: Optional context dictionary for additional parameters
            
        Yields:
            Chunks of generated text as they become available
        """
        # Default fallback: yield entire response at once
        response = await self.generate(prompt, context)
        yield response

