"""Prompt interview routes for conversational prompt building."""

from typing import Annotated
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import require_tenant_admin
from app.persistence.database import get_db
from app.persistence.models.tenant import User
from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus
from app.persistence.repositories.prompt_repository import PromptRepository
from app.llm.gemini_client import GeminiClient
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class ToneChoice(str, Enum):
    """Available tone choices for chatbot personality."""
    FRIENDLY_CASUAL = "friendly_casual"
    PROFESSIONAL_POLISHED = "professional_polished"
    ENTHUSIASTIC_ENERGETIC = "enthusiastic_energetic"
    WARM_NURTURING = "warm_nurturing"
    STRAIGHTFORWARD_EFFICIENT = "straightforward_efficient"


TONE_DESCRIPTIONS = {
    ToneChoice.FRIENDLY_CASUAL: {
        "label": "Friendly & Casual",
        "description": "Warm, conversational, uses contractions",
        "example": "Hey! We'd love to help you out..."
    },
    ToneChoice.PROFESSIONAL_POLISHED: {
        "label": "Professional & Polished", 
        "description": "Courteous but formal, business-like",
        "example": "Thank you for your inquiry. We would be happy to assist..."
    },
    ToneChoice.ENTHUSIASTIC_ENERGETIC: {
        "label": "Enthusiastic & Energetic",
        "description": "Upbeat, excited, uses exclamation points",
        "example": "That's awesome! We can't wait to see you!"
    },
    ToneChoice.WARM_NURTURING: {
        "label": "Warm & Nurturing",
        "description": "Gentle, reassuring, great for kids/families",
        "example": "We completely understand - no worries at all..."
    },
    ToneChoice.STRAIGHTFORWARD_EFFICIENT: {
        "label": "Straightforward & Efficient",
        "description": "Direct, concise, gets to the point",
        "example": "Classes are Mon-Fri 9-5. Pricing starts at $50."
    },
}


class InterviewStep(str, Enum):
    """Steps in the interview process."""
    BUSINESS_NAME = "business_name"
    INDUSTRY = "industry"
    LOCATION = "location"
    PHONE = "phone"
    WEBSITE = "website"
    HOURS = "hours"
    SERVICES = "services"
    PRICING = "pricing"
    FAQ = "faq"
    POLICIES = "policies"
    REQUIREMENTS = "requirements"
    TONE = "tone"
    LEAD_TIMING = "lead_timing"
    ANYTHING_ELSE = "anything_else"
    COMPLETE = "complete"


INTERVIEW_QUESTIONS = {
    InterviewStep.BUSINESS_NAME: {
        "question": "Let's get started! What's the name of your business?",
        "field": "business_name",
        "type": "text"
    },
    InterviewStep.INDUSTRY: {
        "question": "What type of business is this? (e.g., swim school, restaurant, dental office, fitness studio)",
        "field": "industry",
        "type": "text"
    },
    InterviewStep.LOCATION: {
        "question": "Where are you located? Include your full address if you'd like customers to find you easily.",
        "field": "location",
        "type": "text"
    },
    InterviewStep.PHONE: {
        "question": "What's the best phone number for customers to reach you?",
        "field": "phone_number",
        "type": "text"
    },
    InterviewStep.WEBSITE: {
        "question": "Do you have a website? If so, what's the URL?",
        "field": "website_url",
        "type": "text"
    },
    InterviewStep.HOURS: {
        "question": "What are your business hours? You can list them by day (e.g., Mon-Fri 9am-6pm, Sat 10am-4pm, Sun Closed)",
        "field": "business_hours",
        "type": "text"
    },
    InterviewStep.SERVICES: {
        "question": "What services or products do you offer? List your main offerings.",
        "field": "services",
        "type": "text"
    },
    InterviewStep.PRICING: {
        "question": "Can you share your pricing or price ranges? (e.g., 'Private lessons: $50/session, Group classes: $25/session')",
        "field": "pricing",
        "type": "text"
    },
    InterviewStep.FAQ: {
        "question": "What questions do customers ask most frequently? List a few common ones and their answers.",
        "field": "faq",
        "type": "text"
    },
    InterviewStep.POLICIES: {
        "question": "Do you have any important policies customers should know about? (cancellation policy, refund policy, booking requirements, etc.)",
        "field": "policies",
        "type": "text"
    },
    InterviewStep.REQUIREMENTS: {
        "question": "Are there any requirements for your services? (age limits, equipment needed, prerequisites, etc.)",
        "field": "requirements",
        "type": "text"
    },
    InterviewStep.TONE: {
        "question": "How would you like your chatbot to communicate with customers? Choose a personality:",
        "field": "tone",
        "type": "choice",
        "choices": [
            {
                "value": ToneChoice.FRIENDLY_CASUAL.value,
                "label": "Friendly & Casual",
                "description": "Warm, conversational, uses contractions",
                "example": "Hey! We'd love to help you out..."
            },
            {
                "value": ToneChoice.PROFESSIONAL_POLISHED.value,
                "label": "Professional & Polished",
                "description": "Courteous but formal, business-like", 
                "example": "Thank you for your inquiry. We would be happy to assist..."
            },
            {
                "value": ToneChoice.ENTHUSIASTIC_ENERGETIC.value,
                "label": "Enthusiastic & Energetic",
                "description": "Upbeat, excited, uses exclamation points",
                "example": "That's awesome! We can't wait to see you!"
            },
            {
                "value": ToneChoice.WARM_NURTURING.value,
                "label": "Warm & Nurturing",
                "description": "Gentle, reassuring, great for kids/families",
                "example": "We completely understand - no worries at all..."
            },
            {
                "value": ToneChoice.STRAIGHTFORWARD_EFFICIENT.value,
                "label": "Straightforward & Efficient",
                "description": "Direct, concise, gets to the point",
                "example": "Classes are Mon-Fri 9-5. Pricing starts at $50."
            }
        ]
    },
    InterviewStep.LEAD_TIMING: {
        "question": "When should the chatbot ask visitors for their contact information (name and email)? For example: 'After answering their first question' or 'When they ask about pricing' or 'Only if they want to schedule something'",
        "field": "lead_timing",
        "type": "text"
    },
    InterviewStep.ANYTHING_ELSE: {
        "question": "Is there anything else you'd like your chatbot to know or do? Any special instructions, phrases to use, topics to avoid, or other details?",
        "field": "anything_else",
        "type": "text"
    },
}

# Define the order of steps
STEP_ORDER = [
    InterviewStep.BUSINESS_NAME,
    InterviewStep.INDUSTRY,
    InterviewStep.LOCATION,
    InterviewStep.PHONE,
    InterviewStep.WEBSITE,
    InterviewStep.HOURS,
    InterviewStep.SERVICES,
    InterviewStep.PRICING,
    InterviewStep.FAQ,
    InterviewStep.POLICIES,
    InterviewStep.REQUIREMENTS,
    InterviewStep.TONE,
    InterviewStep.LEAD_TIMING,
    InterviewStep.ANYTHING_ELSE,
]


class InterviewState(BaseModel):
    """Current state of the interview."""
    current_step: str
    collected_data: dict = {}
    is_complete: bool = False


class InterviewResponse(BaseModel):
    """Response from interview endpoint."""
    current_step: str
    question: str
    question_type: str  # "text" or "choice"
    choices: list[dict] | None = None
    collected_data: dict
    is_complete: bool
    progress: int  # 0-100


class InterviewAnswerRequest(BaseModel):
    """Request to submit an answer."""
    current_step: str
    answer: str
    collected_data: dict = {}


class GeneratePromptRequest(BaseModel):
    """Request to generate prompt from collected data."""
    collected_data: dict
    prompt_name: str | None = None


class GeneratePromptResponse(BaseModel):
    """Response with generated prompt."""
    bundle_id: int
    name: str
    sections: list[dict]
    message: str


class EditPromptRequest(BaseModel):
    """Request to edit an existing prompt via conversation."""
    edit_instruction: str  # e.g., "Remove the part about cancellation policy"


class EditPromptResponse(BaseModel):
    """Response after editing prompt."""
    bundle_id: int
    updated_sections: list[dict]
    message: str
    changes_made: str


@router.get("/interview/start", response_model=InterviewResponse)
async def start_interview(
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
) -> InterviewResponse:
    """Start a new prompt interview."""
    first_step = STEP_ORDER[0]
    question_data = INTERVIEW_QUESTIONS[first_step]
    
    return InterviewResponse(
        current_step=first_step.value,
        question=question_data["question"],
        question_type=question_data["type"],
        choices=question_data.get("choices"),
        collected_data={},
        is_complete=False,
        progress=0,
    )


@router.post("/interview/answer", response_model=InterviewResponse)
async def submit_answer(
    request: InterviewAnswerRequest,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
) -> InterviewResponse:
    """Submit an answer and get the next question."""
    current_step = InterviewStep(request.current_step)
    
    # Store the answer
    collected_data = request.collected_data.copy()
    field_name = INTERVIEW_QUESTIONS[current_step]["field"]
    collected_data[field_name] = request.answer
    
    # Find next step
    current_index = STEP_ORDER.index(current_step)
    
    if current_index >= len(STEP_ORDER) - 1:
        # Interview complete
        return InterviewResponse(
            current_step=InterviewStep.COMPLETE.value,
            question="Great! I have all the information I need. Click 'Generate Prompt' to create your chatbot prompt.",
            question_type="complete",
            choices=None,
            collected_data=collected_data,
            is_complete=True,
            progress=100,
        )
    
    # Move to next step
    next_step = STEP_ORDER[current_index + 1]
    question_data = INTERVIEW_QUESTIONS[next_step]
    progress = int(((current_index + 1) / len(STEP_ORDER)) * 100)
    
    return InterviewResponse(
        current_step=next_step.value,
        question=question_data["question"],
        question_type=question_data["type"],
        choices=question_data.get("choices"),
        collected_data=collected_data,
        is_complete=False,
        progress=progress,
    )


@router.post("/interview/generate", response_model=GeneratePromptResponse)
async def generate_prompt_from_interview(
    request: GeneratePromptRequest,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GeneratePromptResponse:
    """Generate a prompt bundle from collected interview data."""
    current_user, tenant_id = admin_data
    data = request.collected_data
    
    # Build the prompt sections
    business_name = data.get("business_name", "Your Business")
    tone = data.get("tone", ToneChoice.FRIENDLY_CASUAL.value)
    tone_info = TONE_DESCRIPTIONS.get(ToneChoice(tone), TONE_DESCRIPTIONS[ToneChoice.FRIENDLY_CASUAL])
    
    # Generate system prompt based on tone
    system_content = f"""You are a helpful customer service assistant for {business_name}. 
Your communication style is: {tone_info['label']} - {tone_info['description']}.

Key behaviors:
- Always be helpful and accurate with information about the business
- If you don't know something, say so honestly and offer to help find the answer
- Collect customer name and email when appropriate ({data.get('lead_timing', 'after answering their initial question')})
- Never make up information about services, pricing, or policies
- Keep responses concise but thorough"""

    # Build business info section
    business_info_parts = []
    if data.get("business_name"):
        business_info_parts.append(f"Business Name: {data['business_name']}")
    if data.get("industry"):
        business_info_parts.append(f"Type of Business: {data['industry']}")
    if data.get("location"):
        business_info_parts.append(f"Location: {data['location']}")
    if data.get("phone_number"):
        business_info_parts.append(f"Phone: {data['phone_number']}")
    if data.get("website_url"):
        business_info_parts.append(f"Website: {data['website_url']}")
    if data.get("business_hours"):
        business_info_parts.append(f"Hours: {data['business_hours']}")
    
    business_info_content = "\n".join(business_info_parts)

    # Build services section
    services_content = ""
    if data.get("services"):
        services_content += f"Services/Products Offered:\n{data['services']}"
    if data.get("pricing"):
        services_content += f"\n\nPricing:\n{data['pricing']}"

    # Build FAQ section
    faq_content = ""
    if data.get("faq"):
        faq_content = f"Frequently Asked Questions:\n{data['faq']}"

    # Build policies section
    policies_content = ""
    policies_parts = []
    if data.get("policies"):
        policies_parts.append(f"Policies:\n{data['policies']}")
    if data.get("requirements"):
        policies_parts.append(f"Requirements:\n{data['requirements']}")
    if policies_parts:
        policies_content = "\n\n".join(policies_parts)

    # Build additional instructions
    additional_content = ""
    if data.get("anything_else"):
        additional_content = f"Additional Instructions:\n{data['anything_else']}"

    # Lead capture instructions
    lead_capture_content = f"""Lead Capture Instructions:
- Required information to collect: Customer Name and Email
- When to ask: {data.get('lead_timing', 'After answering their initial question or when they express interest')}
- Be natural when asking for information - don't make it feel like a form
- Example: "I'd be happy to help you with that! Could I get your name and email so I can send you more details?"
"""

    # Create the prompt bundle
    prompt_repo = PromptRepository(db)
    prompt_name = request.prompt_name or f"{business_name} Chatbot"
    
    bundle = await prompt_repo.create(
        tenant_id=tenant_id,
        name=prompt_name,
        version="1.0.0",
        status=PromptStatus.DRAFT.value,
        is_active=False,
    )
    
    # Create sections
    sections_data = [
        {"section_key": "system", "scope": "system", "content": system_content, "order": 0},
        {"section_key": "business_info", "scope": "business_info", "content": business_info_content, "order": 1},
    ]
    
    if services_content:
        sections_data.append({"section_key": "services", "scope": "business_info", "content": services_content, "order": 2})
    
    if faq_content:
        sections_data.append({"section_key": "faq", "scope": "faq", "content": faq_content, "order": 3})
    
    if policies_content:
        sections_data.append({"section_key": "policies", "scope": "custom", "content": policies_content, "order": 4})
    
    sections_data.append({"section_key": "lead_capture", "scope": "custom", "content": lead_capture_content, "order": 5})
    
    if additional_content:
        sections_data.append({"section_key": "additional", "scope": "custom", "content": additional_content, "order": 6})
    
    # Save sections to database
    for section_data in sections_data:
        section = PromptSection(
            bundle_id=bundle.id,
            section_key=section_data["section_key"],
            scope=section_data["scope"],
            content=section_data["content"],
            order=section_data["order"],
        )
        db.add(section)
    
    await db.commit()
    
    return GeneratePromptResponse(
        bundle_id=bundle.id,
        name=prompt_name,
        sections=sections_data,
        message=f"Successfully created prompt '{prompt_name}'. You can now test it or publish it to make it live.",
    )


@router.post("/{bundle_id}/edit", response_model=EditPromptResponse)
async def edit_prompt_via_chat(
    bundle_id: int,
    request: EditPromptRequest,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EditPromptResponse:
    """Edit an existing prompt via natural language instruction."""
    current_user, tenant_id = admin_data
    prompt_repo = PromptRepository(db)
    
    # Get the existing bundle
    bundle = await prompt_repo.get_by_id(bundle_id)
    if not bundle or bundle.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found",
        )
    
    if bundle.status == PromptStatus.PRODUCTION.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit a live prompt. Deactivate it first or create a new draft.",
        )
    
    # Get current sections
    sections = await prompt_repo.get_sections(bundle_id)
    
    # Build context for LLM
    sections_text = "\n\n".join([
        f"=== Section: {s.section_key} ===\n{s.content}"
        for s in sections
    ])
    
    # Use LLM to process the edit request
    llm = GeminiClient()
    
    edit_prompt = f"""You are helping edit a chatbot prompt. Here are the current prompt sections:

{sections_text}

The user wants to make this change: "{request.edit_instruction}"

Please respond with a JSON object containing:
1. "action": one of "update", "remove", or "add"
2. "section_key": which section to modify (or new section name if adding)
3. "new_content": the updated content (null if removing)
4. "explanation": brief explanation of what was changed

If the instruction is unclear, set action to "clarify" and explanation to a question asking for clarification.

Respond ONLY with valid JSON, no other text."""

    try:
        response = await llm.generate(edit_prompt, {"temperature": 0.3, "max_tokens": 2000})
        
        # Parse the response
        import json
        # Clean up response (remove markdown code blocks if present)
        clean_response = response.strip()
        if clean_response.startswith("```"):
            clean_response = clean_response.split("\n", 1)[1]
        if clean_response.endswith("```"):
            clean_response = clean_response.rsplit("\n", 1)[0]
        clean_response = clean_response.replace("```json", "").replace("```", "").strip()
        
        edit_result = json.loads(clean_response)
        
        if edit_result.get("action") == "clarify":
            return EditPromptResponse(
                bundle_id=bundle_id,
                updated_sections=[{"section_key": s.section_key, "content": s.content} for s in sections],
                message=edit_result.get("explanation", "Could you please clarify what you'd like to change?"),
                changes_made="No changes made - clarification needed",
            )
        
        # Apply the edit
        section_key = edit_result.get("section_key")
        action = edit_result.get("action")
        new_content = edit_result.get("new_content")
        
        updated_sections = []
        changes_made = edit_result.get("explanation", "Changes applied")
        
        if action == "remove":
            # Remove the section
            for section in sections:
                if section.section_key == section_key:
                    await db.delete(section)
                else:
                    updated_sections.append({"section_key": section.section_key, "content": section.content})
        
        elif action == "update":
            # Update the section
            for section in sections:
                if section.section_key == section_key:
                    section.content = new_content
                    updated_sections.append({"section_key": section.section_key, "content": new_content})
                else:
                    updated_sections.append({"section_key": section.section_key, "content": section.content})
        
        elif action == "add":
            # Add new section
            new_section = PromptSection(
                bundle_id=bundle_id,
                section_key=section_key,
                scope="custom",
                content=new_content,
                order=len(sections),
            )
            db.add(new_section)
            updated_sections = [{"section_key": s.section_key, "content": s.content} for s in sections]
            updated_sections.append({"section_key": section_key, "content": new_content})
        
        await db.commit()
        
        return EditPromptResponse(
            bundle_id=bundle_id,
            updated_sections=updated_sections,
            message="Prompt updated successfully",
            changes_made=changes_made,
        )
        
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process edit request. Please try rephrasing your instruction.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing edit: {str(e)}",
        )


@router.get("/tone-options")
async def get_tone_options() -> list[dict]:
    """Get available tone options for the interview."""
    return [
        {
            "value": tone.value,
            "label": info["label"],
            "description": info["description"],
            "example": info["example"],
        }
        for tone, info in TONE_DESCRIPTIONS.items()
    ]
