"""LLM client interface."""

from abc import ABC, abstractmethod


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

