"""Chat service for processing web chat requests."""

import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.conversation_service import ConversationService
from app.domain.services.lead_service import LeadService
from app.domain.services.prompt_service import PromptService
from app.llm.orchestrator import LLMOrchestrator
from app.persistence.models.conversation import Conversation, Message
from app.persistence.repositories.tenant_repository import TenantRepository


@dataclass
class ChatResult:
    """Result of a chat request."""
    
    session_id: str
    response: str
    requires_contact_info: bool
    conversation_complete: bool
    lead_captured: bool
    turn_count: int
    llm_latency_ms: float


class ChatService:
    """Service for processing chat requests from web widget."""

    # Guardrails
    MAX_TURNS = 20
    TIMEOUT_SECONDS = 300  # 5 minutes
    FOLLOW_UP_NUDGE_TURN = 3  # After 3 turns, suggest providing contact info

    def __init__(self, session: AsyncSession) -> None:
        """Initialize chat service."""
        self.session = session
        self.conversation_service = ConversationService(session)
        self.lead_service = LeadService(session)
        self.prompt_service = PromptService(session)
        self.llm_orchestrator = LLMOrchestrator()
        self.tenant_repo = TenantRepository(session)

    async def process_chat(
        self,
        tenant_id: int,
        session_id: str | None,
        user_message: str,
        user_name: str | None = None,
        user_email: str | None = None,
        user_phone: str | None = None,
    ) -> ChatResult:
        """Process a chat request.
        
        Args:
            tenant_id: Tenant ID (required)
            session_id: Session ID (creates new conversation if None)
            user_message: User's message
            user_name: Optional user name (for lead capture)
            user_email: Optional user email (for lead capture)
            user_phone: Optional user phone (for lead capture)
            
        Returns:
            ChatResult with response and metadata
            
        Raises:
            ValueError: If tenant not found or invalid request
        """
        # Verify tenant exists and is active
        tenant = await self.tenant_repo.get_by_id(None, tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")
        if not tenant.is_active:
            raise ValueError(f"Tenant {tenant_id} is not active")

        # Get or create conversation
        conversation = await self._get_or_create_conversation(
            tenant_id, session_id
        )
        session_id = str(conversation.id)  # Use conversation ID as session_id

        # Get conversation history
        messages = await self.conversation_service.get_conversation_history(
            tenant_id, conversation.id
        )
        turn_count = len([m for m in messages if m.role == "user"])

        # Check guardrails
        if turn_count >= self.MAX_TURNS:
            return ChatResult(
                session_id=session_id,
                response="Thank you for chatting! I've reached the maximum number of turns. Please contact us directly for further assistance.",
                requires_contact_info=False,
                conversation_complete=True,
                lead_captured=False,
                turn_count=turn_count,
                llm_latency_ms=0.0,
            )

        # Check timeout (conversation age)
        from datetime import datetime, timezone
        conversation_age = (datetime.now(timezone.utc) - conversation.created_at).total_seconds()
        if conversation_age > self.TIMEOUT_SECONDS:
            return ChatResult(
                session_id=session_id,
                response="This conversation has timed out. Please start a new conversation if you need further assistance.",
                requires_contact_info=False,
                conversation_complete=True,
                lead_captured=False,
                turn_count=turn_count,
                llm_latency_ms=0.0,
            )

        # Add user message
        await self.conversation_service.add_message(
            tenant_id, conversation.id, "user", user_message
        )

        # Handle lead capture
        lead_captured = False
        if user_name or user_email or user_phone:
            # Check if lead already exists for this conversation
            existing_lead = await self.lead_service.get_lead_by_conversation(
                tenant_id, conversation.id
            )
            
            if not existing_lead:
                # Capture lead
                await self.lead_service.capture_lead(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    email=user_email,
                    phone=user_phone,
                    name=user_name,
                )
                lead_captured = True

        # Check if we need to ask for contact info
        requires_contact_info = False
        if not lead_captured and turn_count >= self.FOLLOW_UP_NUDGE_TURN:
            # Check if we already have a lead for this conversation
            existing_lead = await self.lead_service.get_lead_by_conversation(
                tenant_id, conversation.id
            )
            if not existing_lead:
                requires_contact_info = True

        # Use core chat processing logic
        llm_response, llm_latency_ms = await self._process_chat_core(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            user_message=user_message,
            messages=messages,
            system_prompt_method=self.prompt_service.compose_prompt,
            requires_contact_info=requires_contact_info,
        )

        # Add assistant response
        await self.conversation_service.add_message(
            tenant_id, conversation.id, "assistant", llm_response
        )

        # If we need contact info, append a nudge
        final_response = llm_response
        if requires_contact_info and not lead_captured:
            final_response += "\n\nTo help you better, could you please provide your name and email or phone number?"

        return ChatResult(
            session_id=session_id,
            response=final_response,
            requires_contact_info=requires_contact_info and not lead_captured,
            conversation_complete=False,
            lead_captured=lead_captured,
            turn_count=turn_count + 1,
            llm_latency_ms=llm_latency_ms,
        )

    async def _get_or_create_conversation(
        self, tenant_id: int, session_id: str | None
    ) -> Conversation:
        """Get existing conversation or create new one.
        
        Args:
            tenant_id: Tenant ID
            session_id: Session ID (conversation ID as string)
            
        Returns:
            Conversation
        """
        if session_id:
            try:
                conversation_id = int(session_id)
                conversation = await self.conversation_service.get_conversation(
                    tenant_id, conversation_id
                )
                if conversation:
                    return conversation
            except ValueError:
                pass  # Invalid session_id, create new
        
        # Create new conversation
        return await self.conversation_service.create_conversation(
            tenant_id=tenant_id,
            channel="web",
            external_id=None,
        )

    def _build_conversation_context(
        self,
        system_prompt: str,
        messages: list[Message],
        current_user_message: str,
        requires_contact_info: bool,
        additional_context: str | None = None,
    ) -> str:
        """Build conversation context for LLM.
        
        Args:
            system_prompt: System prompt from tenant settings
            messages: Previous messages in conversation
            current_user_message: Current user message
            requires_contact_info: Whether we need to ask for contact info
            
        Returns:
            Full prompt string for LLM
        """
        # Build conversation history
        conversation_history = []
        for msg in messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            conversation_history.append(f"{role_label}: {msg.content}")
        
        # Add current user message
        conversation_history.append(f"User: {current_user_message}")
        
        # Build full prompt
        prompt_parts = [system_prompt]
        
        if conversation_history:
            prompt_parts.append("\n\nConversation History:")
            prompt_parts.append("\n".join(conversation_history))
        
        if requires_contact_info:
            prompt_parts.append(
                "\n\nNote: If the user seems interested or asks about services/products, "
                "politely ask for their name and contact information (email or phone) to help them better."
            )
        
        if additional_context:
            prompt_parts.append(f"\n\n{additional_context}")
        
        prompt_parts.append("\n\nAssistant:")
        
        return "\n".join(prompt_parts)

    async def _process_chat_core(
        self,
        tenant_id: int,
        conversation_id: int,
        user_message: str,
        messages: list[Message],
        system_prompt_method,
        requires_contact_info: bool = False,
        additional_context: str | None = None,
    ) -> tuple[str, float]:
        """Core chat processing logic (reusable for web and SMS).
        
        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID
            user_message: User's message
            messages: Previous messages in conversation
            system_prompt_method: Method to get system prompt (compose_prompt or compose_prompt_sms)
            requires_contact_info: Whether to ask for contact info
            additional_context: Additional context to add to prompt
            
        Returns:
            Tuple of (llm_response, llm_latency_ms)
        """
        # Assemble prompt with conversation history
        system_prompt = await system_prompt_method(tenant_id)
        
        # Build conversation context for LLM
        conversation_context = self._build_conversation_context(
            system_prompt, messages, user_message, requires_contact_info, additional_context
        )

        # Call LLM
        llm_start = time.time()
        try:
            llm_response = await self.llm_orchestrator.generate(
                conversation_context,
                context={"temperature": 0.3, "max_tokens": 500},  # Deterministic defaults
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"LLM generation failed: {e}", exc_info=True)
            llm_response = "I apologize, but I'm having trouble processing your request right now. Please try again in a moment."
        
        llm_latency_ms = (time.time() - llm_start) * 1000
        
        return llm_response, llm_latency_ms

