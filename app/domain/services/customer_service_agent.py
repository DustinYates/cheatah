"""Customer service agent for handling existing customer inquiries."""

import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.prompt_service import PromptService
from app.domain.services.zapier_integration_service import ZapierIntegrationService
from app.llm.orchestrator import LLMOrchestrator
from app.persistence.models.jackrabbit_customer import JackrabbitCustomer
from app.persistence.repositories.conversation_repository import ConversationRepository
from app.persistence.repositories.customer_service_config_repository import CustomerServiceConfigRepository

logger = logging.getLogger(__name__)


@dataclass
class CustomerServiceResult:
    """Result of customer service processing."""
    response_message: str
    source: str  # "jackrabbit", "llm_fallback", "pending_lookup", "error"
    jackrabbit_customer_id: str | None = None
    query_correlation_id: str | None = None
    requires_followup: bool = False
    latency_ms: float = 0.0


class CustomerServiceAgent:
    """Agent for handling customer service inquiries via Jackrabbit/Zapier."""

    # Keywords that indicate account-specific queries (should go to Jackrabbit)
    ACCOUNT_KEYWORDS = [
        "balance", "owe", "payment", "bill", "invoice", "charge",
        "schedule", "class", "lesson", "session", "appointment",
        "enroll", "enrollment", "register", "registration",
        "cancel", "reschedule", "makeup", "make-up",
        "membership", "account", "my", "mine",
        "child", "kid", "son", "daughter", "student",
        "credit", "refund", "receipt",
    ]

    # Default customer service prompt
    DEFAULT_PROMPT = """You are a friendly customer service assistant for {business_name}.
You are helping an existing customer named {customer_name}.

IMPORTANT GUIDELINES:
- Be friendly, professional, and helpful
- You are speaking with an existing customer, not a new lead
- Address them by name when appropriate
- For specific account questions (billing, schedules, etc.), indicate you'll look up their information
- For general questions, provide helpful answers based on the business information

CUSTOMER INFORMATION:
{customer_context}

BUSINESS INFORMATION:
{business_facts}

CONVERSATION HISTORY:
{conversation_history}

Customer's message: {user_message}

Provide a helpful response:"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.zapier_service = ZapierIntegrationService(session)
        self.llm_orchestrator = LLMOrchestrator()
        self.prompt_service = PromptService(session)
        self.config_repo = CustomerServiceConfigRepository(session)
        self.conversation_repo = ConversationRepository(session)

    async def process_inquiry(
        self,
        tenant_id: int,
        jackrabbit_customer: JackrabbitCustomer,
        user_message: str,
        conversation_id: int | None = None,
        channel: str = "sms",
    ) -> CustomerServiceResult:
        """Process a customer service inquiry.

        Routes query to Jackrabbit first, uses LLM fallback for generic questions.

        Args:
            tenant_id: Tenant ID
            jackrabbit_customer: Verified Jackrabbit customer
            user_message: Customer's message/query
            conversation_id: Conversation ID for context
            channel: Communication channel ("sms" or "voice")

        Returns:
            CustomerServiceResult with response
        """
        start_time = time.time()

        # Get tenant config
        config = await self.config_repo.get_by_tenant_id(tenant_id)
        if not config:
            return CustomerServiceResult(
                response_message="I apologize, but I'm having trouble accessing your account information. Please try again later.",
                source="error",
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Get conversation history if available
        conversation_history = await self._get_conversation_history(
            tenant_id, conversation_id
        )

        # Route all queries to Jackrabbit first (per user requirement)
        jackrabbit_response = await self._query_jackrabbit(
            tenant_id=tenant_id,
            customer=jackrabbit_customer,
            query=user_message,
            context={
                "channel": channel,
                "conversation_history": conversation_history,
            },
            timeout_seconds=config.query_timeout_seconds,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        if jackrabbit_response and jackrabbit_response.get("has_answer"):
            # Jackrabbit provided an answer
            answer = jackrabbit_response.get("answer", "")
            return CustomerServiceResult(
                response_message=answer,
                source="jackrabbit",
                jackrabbit_customer_id=jackrabbit_customer.jackrabbit_id,
                query_correlation_id=jackrabbit_response.get("correlation_id"),
                latency_ms=elapsed_ms,
            )

        # Jackrabbit didn't have the answer - use LLM fallback if enabled
        if config.llm_fallback_enabled:
            llm_response = await self._llm_fallback(
                tenant_id=tenant_id,
                customer=jackrabbit_customer,
                user_message=user_message,
                conversation_history=conversation_history,
                custom_prompt=config.llm_fallback_prompt_override,
            )

            elapsed_ms = (time.time() - start_time) * 1000

            return CustomerServiceResult(
                response_message=llm_response,
                source="llm_fallback",
                jackrabbit_customer_id=jackrabbit_customer.jackrabbit_id,
                latency_ms=elapsed_ms,
            )

        # No LLM fallback - return generic message
        return CustomerServiceResult(
            response_message="I'm sorry, I don't have information about that. Please contact us directly for assistance.",
            source="error",
            jackrabbit_customer_id=jackrabbit_customer.jackrabbit_id,
            latency_ms=elapsed_ms,
        )

    async def _query_jackrabbit(
        self,
        tenant_id: int,
        customer: JackrabbitCustomer,
        query: str,
        context: dict,
        timeout_seconds: int = 45,
    ) -> dict | None:
        """Query Jackrabbit via Zapier for account-specific info.

        Args:
            tenant_id: Tenant ID
            customer: Jackrabbit customer
            query: User's query
            context: Additional context
            timeout_seconds: Query timeout

        Returns:
            Response dict with answer, or None if not applicable
        """
        result = await self.zapier_service.send_customer_query(
            tenant_id=tenant_id,
            jackrabbit_customer_id=customer.jackrabbit_id,
            query=query,
            context={
                "customer_name": customer.name,
                "customer_email": customer.email,
                "customer_phone": customer.phone_number,
                "customer_data": customer.customer_data,
                **context,
            },
            conversation_id=context.get("conversation_id"),
            phone_number=customer.phone_number,
        )

        if not result.success:
            logger.warning(
                f"Jackrabbit query failed",
                extra={
                    "tenant_id": tenant_id,
                    "error": result.error,
                    "jackrabbit_id": customer.jackrabbit_id,
                },
            )
            return None

        # Wait for response
        response = await self.zapier_service.wait_for_response(
            correlation_id=result.correlation_id,
            timeout_seconds=timeout_seconds,
        )

        if not response:
            logger.warning(
                f"Jackrabbit query timeout",
                extra={
                    "tenant_id": tenant_id,
                    "jackrabbit_id": customer.jackrabbit_id,
                },
            )
            return None

        return {
            "has_answer": response.get("data", {}).get("has_answer", False),
            "answer": response.get("data", {}).get("answer", ""),
            "correlation_id": result.correlation_id,
        }

    async def _llm_fallback(
        self,
        tenant_id: int,
        customer: JackrabbitCustomer,
        user_message: str,
        conversation_history: list,
        custom_prompt: str | None = None,
    ) -> str:
        """Generate LLM response for questions.

        Uses customer context and business facts.

        Args:
            tenant_id: Tenant ID
            customer: Jackrabbit customer
            user_message: User's message
            conversation_history: Previous messages
            custom_prompt: Optional custom prompt override

        Returns:
            LLM-generated response
        """
        # Get business facts from prompt service
        try:
            business_facts = await self.prompt_service.get_tenant_facts(tenant_id)
        except Exception as e:
            logger.warning(f"Failed to get business facts: {e}")
            business_facts = ""

        # Build customer context
        customer_context = self._build_customer_context(customer)

        # Format conversation history
        history_text = self._format_conversation_history(conversation_history)

        # Get business name
        business_name = "our business"
        if customer.customer_data and customer.customer_data.get("business_name"):
            business_name = customer.customer_data.get("business_name")

        # Build prompt
        prompt_template = custom_prompt or self.DEFAULT_PROMPT
        prompt = prompt_template.format(
            business_name=business_name,
            customer_name=customer.name or "valued customer",
            customer_context=customer_context,
            business_facts=business_facts,
            conversation_history=history_text,
            user_message=user_message,
        )

        try:
            response = await self.llm_orchestrator.generate(prompt)
            return response.strip()
        except Exception as e:
            logger.exception(f"LLM generation failed: {e}")
            return "I apologize, but I'm having trouble processing your request. Please try again or contact us directly."

    def _build_customer_context(self, customer: JackrabbitCustomer) -> str:
        """Build context string from customer data for LLM.

        Args:
            customer: Jackrabbit customer

        Returns:
            Formatted customer context string
        """
        lines = []

        if customer.name:
            lines.append(f"Name: {customer.name}")
        if customer.email:
            lines.append(f"Email: {customer.email}")
        if customer.phone_number:
            lines.append(f"Phone: {customer.phone_number}")

        # Add additional data from customer_data if available
        if customer.customer_data:
            for key, value in customer.customer_data.items():
                if key not in ["name", "email", "phone", "phone_number"]:
                    # Format key nicely
                    formatted_key = key.replace("_", " ").title()
                    lines.append(f"{formatted_key}: {value}")

        return "\n".join(lines) if lines else "No additional customer information available."

    def _format_conversation_history(self, history: list) -> str:
        """Format conversation history for prompt.

        Args:
            history: List of message dicts

        Returns:
            Formatted history string
        """
        if not history:
            return "No previous messages."

        lines = []
        for msg in history[-10:]:  # Last 10 messages
            role = msg.get("role", "user")
            content = msg.get("content", "")
            lines.append(f"{role.title()}: {content}")

        return "\n".join(lines)

    async def _get_conversation_history(
        self,
        tenant_id: int,
        conversation_id: int | None,
    ) -> list:
        """Get conversation history for context.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID

        Returns:
            List of message dicts
        """
        if not conversation_id:
            return []

        try:
            conversation = await self.conversation_repo.get_by_id(
                tenant_id, conversation_id
            )
            if not conversation or not conversation.messages:
                return []

            return [
                {"role": msg.role, "content": msg.content}
                for msg in conversation.messages[-10:]
            ]
        except Exception as e:
            logger.warning(f"Failed to get conversation history: {e}")
            return []

    def _is_account_query(self, message: str) -> bool:
        """Determine if message is an account-specific query.

        Args:
            message: User message

        Returns:
            True if message appears to be account-specific
        """
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in self.ACCOUNT_KEYWORDS)
