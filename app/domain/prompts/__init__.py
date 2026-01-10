"""JSON-based prompt system for ChatterCheetah.

This module provides a structured approach to prompt management:
- Base configs: Hardcoded rules for conversation flow, safety, style
- Tenant configs: JSON stored in database for business-specific data
- Assembler: Combines base + tenant at runtime into final prompt
"""

from app.domain.prompts.assembler import PromptAssembler

__all__ = ["PromptAssembler"]
