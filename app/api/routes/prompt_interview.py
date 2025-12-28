"""Prompt interview routes for conversational prompt building."""

import re
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
    LOCATION_ADDITIONAL = "location_additional"  # "Do you have more locations?"
    LOCATION_NEXT = "location_next"  # For collecting additional locations
    PHONE = "phone"
    WEBSITE = "website"
    # Class/program collection
    CLASSES_LIST = "classes_list"  # "What classes do you offer?"
    CLASS_URL = "class_url"  # "What's the URL for [class]?"
    CLASSES_MORE = "classes_more"  # "Any more classes?"
    HOURS = "hours"
    # Pool-specific hours
    POOL_HOURS_CHECK = "pool_hours_check"  # "Do you have pool-specific hours?"
    POOL_NAME = "pool_name"  # "What's the name of this pool?"
    POOL_HOURS = "pool_hours"  # "What are the hours for [pool]?"
    POOL_MORE = "pool_more"  # "Any more pools?"
    SERVICES = "services"
    SERVICE_PITCH = "service_pitch"  # "What's the sales pitch for [service]?"
    SERVICES_MORE = "services_more"  # "Any more services to describe?"
    PRICING = "pricing"
    # Interactive FAQ collection
    FAQ_QUESTION = "faq_question"  # "What's a common question customers ask?"
    FAQ_ANSWER = "faq_answer"  # "What's your answer to that?"
    FAQ_MORE = "faq_more"  # "Any more FAQs?"
    # Individual policy questions
    CANCELLATION_POLICY = "cancellation_policy"
    REFUND_POLICY = "refund_policy"
    BOOKING_REQUIREMENTS = "booking_requirements"
    OTHER_POLICIES = "other_policies"
    # Individual requirement questions
    AGE_REQUIREMENTS = "age_requirements"
    EQUIPMENT_NEEDED = "equipment_needed"
    PREREQUISITES = "prerequisites"
    OTHER_REQUIREMENTS = "other_requirements"
    TONE = "tone"
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
    InterviewStep.LOCATION_ADDITIONAL: {
        "question": "Do you have additional locations?",
        "field": "has_additional_locations",
        "type": "choice",
        "choices": [
            {"value": "yes", "label": "Yes", "description": "I have more locations to add"},
            {"value": "no", "label": "No", "description": "This is my only location"},
        ]
    },
    InterviewStep.LOCATION_NEXT: {
        "question": "What's the address of your next location?",
        "field": "location_next",
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
    # Class/program collection
    InterviewStep.CLASSES_LIST: {
        "question": """Which classes and programs do you offer? Please list all levels you currently run (one per line). If you're not sure, start with the age groups you serve.

Examples by age group:
• Infant (3 months–36 months)
• Child (3 years–11 years)
• Teen (12 years–17 years)
• Adult (18+)

Example class levels:
• Tadpole, Swimboree, Seahorse, Starfish, Minnow
• Turtle 1, Turtle 2, Shark 1, Shark 2
• Young Adult Level 1/2/3, Adult Level 1/2/3

Specialty programs:
• Private Lessons
• Adaptive Aquatics / Special Needs Lessons
• Swim Team / Barracudas Program
• Stroke Development
• Water Safety / Survival Skills""",
        "field": "class_name",
        "type": "text"
    },
    InterviewStep.CLASS_URL: {
        "question": "What's the registration or signup URL for this class? (Leave blank if none)",
        "field": "class_url",
        "type": "text"
    },
    InterviewStep.CLASSES_MORE: {
        "question": "Do you have other classes or programs to add?",
        "field": "has_more_classes",
        "type": "choice",
        "choices": [
            {"value": "yes", "label": "Yes", "description": "I have more classes to add"},
            {"value": "no", "label": "No", "description": "That's all my classes"},
        ]
    },
    InterviewStep.HOURS: {
        "question": "What are your general business hours? (e.g., Mon-Fri 9am-6pm, Sat 10am-4pm, Sun Closed)",
        "field": "business_hours",
        "type": "text"
    },
    # Pool-specific hours
    InterviewStep.POOL_HOURS_CHECK: {
        "question": "Do you have specific pool hours that differ from your business hours?",
        "field": "has_pool_hours",
        "type": "choice",
        "choices": [
            {"value": "yes", "label": "Yes", "description": "Our pool hours are different from business hours"},
            {"value": "no", "label": "No", "description": "Pool hours match our business hours"},
            {"value": "skip", "label": "Not Applicable", "description": "We don't have pools"},
        ]
    },
    InterviewStep.POOL_NAME: {
        "question": "What's the pool name/identifier and the facility/location? (Example: 'LA Fitness Cypress – 12304 Barker Cypress Rd., Cypress, TX 77433' or 'LA Fitness Langham Creek off FM 529')",
        "field": "pool_name",
        "type": "text"
    },
    InterviewStep.POOL_HOURS: {
        "question": "What are the hours for this pool?",
        "field": "pool_hours_value",
        "type": "text"
    },
    InterviewStep.POOL_MORE: {
        "question": "Do you have another pool with different hours?",
        "field": "has_more_pools",
        "type": "choice",
        "choices": [
            {"value": "yes", "label": "Yes", "description": "I have more pools to add"},
            {"value": "no", "label": "No", "description": "That's all my pools"},
        ]
    },
    InterviewStep.SERVICES: {
        "question": "What services or products do you offer? (List one main service, e.g., 'Private Swim Lessons')",
        "field": "service_name",
        "type": "text"
    },
    InterviewStep.SERVICE_PITCH: {
        "question": "What's your sales pitch for this service? What makes it special or why should customers choose it?",
        "field": "service_pitch_value",
        "type": "text"
    },
    InterviewStep.SERVICES_MORE: {
        "question": "Do you have other services to describe?",
        "field": "has_more_services",
        "type": "choice",
        "choices": [
            {"value": "yes", "label": "Yes", "description": "I have more services to add"},
            {"value": "no", "label": "No", "description": "That's all my services"},
        ]
    },
    InterviewStep.PRICING: {
        "question": "Can you share your pricing or price ranges? Please include monthly tuition examples (e.g., 1x/week ≈ $140/month; 2x/week ≈ $266/month; registration fee, sibling/multi-class discounts if applicable). Example formats: '1x/week: $35/lesson (~$140/month)' or 'Registration fee: $60 per swimmer / $90 family max'.",
        "field": "pricing",
        "type": "text"
    },
    # Interactive FAQ collection
    InterviewStep.FAQ_QUESTION: {
        "question": "What's a common question that customers ask? (e.g., 'Do I need to bring my own goggles?')",
        "field": "faq_question_value",
        "type": "text"
    },
    InterviewStep.FAQ_ANSWER: {
        "question": "What's your answer to that question?",
        "field": "faq_answer_value",
        "type": "text"
    },
    InterviewStep.FAQ_MORE: {
        "question": "Any other FAQ you'd like included for families? Common FAQs include: makeup classes/reschedules, missed class policy, water temperature, what to bring, diaper policy, instructor qualifications, group size ratios, trial/observation policy, and private lesson availability.",
        "field": "has_more_faqs",
        "type": "choice",
        "choices": [
            {"value": "yes", "label": "Yes", "description": "I have more FAQs to add"},
            {"value": "no", "label": "No", "description": "That's all my FAQs"},
        ]
    },
    # Individual Policy Questions
    InterviewStep.CANCELLATION_POLICY: {
        "question": "What is your cancellation/withdrawal policy? Include required notice and how it relates to the billing cycle (example: '30-day notice required; submit before the 20th to avoid next month's billing' or 'cancel one month before the last billing cycle').",
        "field": "cancellation_policy",
        "type": "text"
    },
    InterviewStep.REFUND_POLICY: {
        "question": "What is your refund policy? (e.g., 'Full refund within 7 days', 'No refunds, store credit only', etc.)",
        "field": "refund_policy",
        "type": "text"
    },
    InterviewStep.BOOKING_REQUIREMENTS: {
        "question": "Are there any booking or scheduling requirements? (e.g., 'Must book 48 hours in advance', 'Deposit required', etc.)",
        "field": "booking_requirements",
        "type": "text"
    },
    InterviewStep.OTHER_POLICIES: {
        "question": "Any other policies customers should know about? (late fees, dress code, etc.)",
        "field": "other_policies",
        "type": "text"
    },
    # Individual Requirement Questions
    InterviewStep.AGE_REQUIREMENTS: {
        "question": "Are there any age requirements for your services? (e.g., 'Must be 18+', 'Children under 12 require adult supervision', etc.)",
        "field": "age_requirements",
        "type": "text"
    },
    InterviewStep.EQUIPMENT_NEEDED: {
        "question": """What equipment or items should swimmers bring?

Common items for swim schools:
• Swimsuit
• Towel
• Swim cap (provided at first lesson? required for class?)
• Goggles (required for which levels? optional for lower levels?)
• Swim diapers for non-potty-trained swimmers (disposable + reusable?)
• Optional tighter-fitting cap for long/thick hair""",
        "field": "equipment_needed",
        "type": "text"
    },
    InterviewStep.PREREQUISITES: {
        "question": "Are there any prerequisites or prior experience required—or is placement based on age and comfort level? (e.g., 'beginner-friendly; we place swimmers by age + water comfort + floating/submersion skills')",
        "field": "prerequisites",
        "type": "text"
    },
    InterviewStep.OTHER_REQUIREMENTS: {
        "question": "Any other requirements or things customers should know before their visit?",
        "field": "other_requirements",
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
    InterviewStep.ANYTHING_ELSE: {
        "question": "Is there anything else you'd like your chatbot to know or do? Any special instructions, phrases to use, topics to avoid, or other details?",
        "field": "anything_else",
        "type": "text"
    },
}

# Define the base order of steps (dynamic steps handled in submit_answer)
STEP_ORDER = [
    InterviewStep.BUSINESS_NAME,
    InterviewStep.INDUSTRY,
    InterviewStep.LOCATION,
    InterviewStep.LOCATION_ADDITIONAL,
    # LOCATION_NEXT is dynamic - loops back to LOCATION_ADDITIONAL
    InterviewStep.PHONE,
    InterviewStep.WEBSITE,
    InterviewStep.CLASSES_LIST,
    InterviewStep.CLASS_URL,
    InterviewStep.CLASSES_MORE,
    # CLASSES_LIST/CLASS_URL loop back to CLASSES_MORE
    InterviewStep.HOURS,
    InterviewStep.POOL_HOURS_CHECK,
    # POOL_NAME, POOL_HOURS, POOL_MORE are dynamic loops
    InterviewStep.SERVICES,
    InterviewStep.SERVICE_PITCH,
    InterviewStep.SERVICES_MORE,
    # SERVICES/SERVICE_PITCH loop back to SERVICES_MORE
    InterviewStep.PRICING,
    InterviewStep.FAQ_QUESTION,
    InterviewStep.FAQ_ANSWER,
    InterviewStep.FAQ_MORE,
    # FAQ_QUESTION/FAQ_ANSWER loop back to FAQ_MORE
    # Individual policy questions
    InterviewStep.CANCELLATION_POLICY,
    InterviewStep.REFUND_POLICY,
    InterviewStep.BOOKING_REQUIREMENTS,
    InterviewStep.OTHER_POLICIES,
    # Individual requirement questions
    InterviewStep.AGE_REQUIREMENTS,
    InterviewStep.EQUIPMENT_NEEDED,
    InterviewStep.PREREQUISITES,
    InterviewStep.OTHER_REQUIREMENTS,
    InterviewStep.TONE,
    InterviewStep.ANYTHING_ELSE,
]

# Steps that are part of loops (not in main order for progress calculation)
LOOP_STEPS = {
    InterviewStep.LOCATION_NEXT,
    InterviewStep.POOL_NAME,
    InterviewStep.POOL_HOURS,
    InterviewStep.POOL_MORE,
}


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


def get_next_step_and_question(
    current_step: InterviewStep,
    answer: str,
    collected_data: dict,
) -> tuple[InterviewStep, dict, str | None]:
    """
    Determine the next step based on current step and answer.
    Returns (next_step, question_data, dynamic_question_override).
    """
    # Handle dynamic branching based on current step and answer
    
    # Location branching
    if current_step == InterviewStep.LOCATION_ADDITIONAL:
        if answer == "yes":
            # Initialize locations list if needed
            if "locations" not in collected_data:
                collected_data["locations"] = [collected_data.get("location", "")]
            return InterviewStep.LOCATION_NEXT, INTERVIEW_QUESTIONS[InterviewStep.LOCATION_NEXT], None
        else:
            return InterviewStep.PHONE, INTERVIEW_QUESTIONS[InterviewStep.PHONE], None
    
    if current_step == InterviewStep.LOCATION_NEXT:
        # Store the additional location
        if "locations" not in collected_data:
            collected_data["locations"] = [collected_data.get("location", "")]
        collected_data["locations"].append(answer)
        # Ask if there are more locations
        return InterviewStep.LOCATION_ADDITIONAL, INTERVIEW_QUESTIONS[InterviewStep.LOCATION_ADDITIONAL], None
    
    # Classes branching
    if current_step == InterviewStep.CLASSES_LIST:
        # Parse the answer into individual classes (split by newlines, commas, or bullet points)
        # Split by newlines, then clean up each line
        raw_classes = re.split(r'[\n\r]+', answer)
        parsed_classes = []
        for line in raw_classes:
            # Remove bullet points, numbers, and leading/trailing whitespace
            line = re.sub(r'^[\s•\-\*\d\.]+', '', line).strip()
            if line:
                # If the line contains commas, it might be a list like "Tadpole, Swimboree, Seahorse"
                # But also might be "Turtle 1, Turtle 2" which are separate classes
                # Split by comma only if the parts look like separate class names
                if ',' in line:
                    parts = [p.strip() for p in line.split(',')]
                    # Add each part as a separate class
                    parsed_classes.extend([p for p in parts if p])
                else:
                    parsed_classes.append(line)

        # Store the pending classes queue
        if parsed_classes:
            collected_data["_pending_classes"] = parsed_classes[1:]  # Rest of classes
            collected_data["_current_class_name"] = parsed_classes[0]  # First class
            return InterviewStep.CLASS_URL, INTERVIEW_QUESTIONS[InterviewStep.CLASS_URL], f"What's the registration or signup URL for '{parsed_classes[0]}'? (Leave blank if none)"
        else:
            # No valid classes parsed, ask again
            return InterviewStep.CLASSES_LIST, INTERVIEW_QUESTIONS[InterviewStep.CLASSES_LIST], "I didn't catch any class names. What classes or programs do you offer? (List one per line)"

    if current_step == InterviewStep.CLASS_URL:
        # Store the class with its URL
        if "classes" not in collected_data:
            collected_data["classes"] = []
        class_name = collected_data.pop("_current_class_name", "Unknown Class")
        collected_data["classes"].append({"name": class_name, "url": answer or ""})

        # Check if there are more pending classes from the initial batch
        pending_classes = collected_data.get("_pending_classes", [])
        if pending_classes:
            # Pop the next class from the queue
            next_class = pending_classes.pop(0)
            collected_data["_pending_classes"] = pending_classes
            collected_data["_current_class_name"] = next_class
            return InterviewStep.CLASS_URL, INTERVIEW_QUESTIONS[InterviewStep.CLASS_URL], f"What's the registration or signup URL for '{next_class}'? (Leave blank if none)"
        else:
            # No more pending classes, ask if they have more to add
            collected_data.pop("_pending_classes", None)  # Clean up
            return InterviewStep.CLASSES_MORE, INTERVIEW_QUESTIONS[InterviewStep.CLASSES_MORE], None

    if current_step == InterviewStep.CLASSES_MORE:
        if answer == "yes":
            return InterviewStep.CLASSES_LIST, INTERVIEW_QUESTIONS[InterviewStep.CLASSES_LIST], "What's the name of the next class or program? (You can list multiple, one per line)"
        else:
            return InterviewStep.HOURS, INTERVIEW_QUESTIONS[InterviewStep.HOURS], None
    
    # Pool hours branching
    if current_step == InterviewStep.POOL_HOURS_CHECK:
        if answer == "yes":
            return InterviewStep.POOL_NAME, INTERVIEW_QUESTIONS[InterviewStep.POOL_NAME], None
        else:
            return InterviewStep.SERVICES, INTERVIEW_QUESTIONS[InterviewStep.SERVICES], None
    
    if current_step == InterviewStep.POOL_NAME:
        collected_data["_current_pool_name"] = answer
        return InterviewStep.POOL_HOURS, INTERVIEW_QUESTIONS[InterviewStep.POOL_HOURS], f"What are the hours for '{answer}'?"
    
    if current_step == InterviewStep.POOL_HOURS:
        if "pool_hours" not in collected_data:
            collected_data["pool_hours"] = []
        pool_name = collected_data.pop("_current_pool_name", "Pool")
        collected_data["pool_hours"].append({"name": pool_name, "hours": answer})
        return InterviewStep.POOL_MORE, INTERVIEW_QUESTIONS[InterviewStep.POOL_MORE], None
    
    if current_step == InterviewStep.POOL_MORE:
        if answer == "yes":
            return InterviewStep.POOL_NAME, INTERVIEW_QUESTIONS[InterviewStep.POOL_NAME], "What's the pool name/identifier and the facility/location for the next pool?"
        else:
            return InterviewStep.SERVICES, INTERVIEW_QUESTIONS[InterviewStep.SERVICES], None
    
    # Services branching
    if current_step == InterviewStep.SERVICES:
        collected_data["_current_service_name"] = answer
        return InterviewStep.SERVICE_PITCH, INTERVIEW_QUESTIONS[InterviewStep.SERVICE_PITCH], f"What's your sales pitch for '{answer}'? What makes it special or why should customers choose it?"
    
    if current_step == InterviewStep.SERVICE_PITCH:
        if "services_list" not in collected_data:
            collected_data["services_list"] = []
        service_name = collected_data.pop("_current_service_name", "Service")
        collected_data["services_list"].append({"name": service_name, "pitch": answer})
        return InterviewStep.SERVICES_MORE, INTERVIEW_QUESTIONS[InterviewStep.SERVICES_MORE], None
    
    if current_step == InterviewStep.SERVICES_MORE:
        if answer == "yes":
            return InterviewStep.SERVICES, INTERVIEW_QUESTIONS[InterviewStep.SERVICES], "What's the name of your next service or product?"
        else:
            return InterviewStep.PRICING, INTERVIEW_QUESTIONS[InterviewStep.PRICING], None
    
    # FAQ branching
    if current_step == InterviewStep.FAQ_QUESTION:
        collected_data["_current_faq_question"] = answer
        return InterviewStep.FAQ_ANSWER, INTERVIEW_QUESTIONS[InterviewStep.FAQ_ANSWER], None
    
    if current_step == InterviewStep.FAQ_ANSWER:
        if "faqs" not in collected_data:
            collected_data["faqs"] = []
        faq_question = collected_data.pop("_current_faq_question", "Question")
        collected_data["faqs"].append({"question": faq_question, "answer": answer})
        return InterviewStep.FAQ_MORE, INTERVIEW_QUESTIONS[InterviewStep.FAQ_MORE], None
    
    if current_step == InterviewStep.FAQ_MORE:
        if answer == "yes":
            return InterviewStep.FAQ_QUESTION, INTERVIEW_QUESTIONS[InterviewStep.FAQ_QUESTION], "What's another common question customers ask?"
        else:
            return InterviewStep.CANCELLATION_POLICY, INTERVIEW_QUESTIONS[InterviewStep.CANCELLATION_POLICY], None
    
    # Default: move to next step in order
    if current_step in STEP_ORDER:
        current_index = STEP_ORDER.index(current_step)
        if current_index < len(STEP_ORDER) - 1:
            next_step = STEP_ORDER[current_index + 1]
            return next_step, INTERVIEW_QUESTIONS[next_step], None
    
    # If we reach here, interview is complete
    return InterviewStep.COMPLETE, {}, None


@router.post("/interview/answer", response_model=InterviewResponse)
async def submit_answer(
    request: InterviewAnswerRequest,
    admin_data: Annotated[tuple[User, int], Depends(require_tenant_admin)],
) -> InterviewResponse:
    """Submit an answer and get the next question."""
    current_step = InterviewStep(request.current_step)
    
    # Store the answer (for non-dynamic fields)
    collected_data = request.collected_data.copy()
    if current_step in INTERVIEW_QUESTIONS:
        field_name = INTERVIEW_QUESTIONS[current_step]["field"]
        # Don't overwrite structured data with temporary field values
        if not field_name.startswith("_") and field_name not in ["class_name", "class_url", "service_name", "service_pitch_value", "faq_question_value", "faq_answer_value", "pool_name", "pool_hours_value", "location_next", "has_additional_locations", "has_more_classes", "has_pool_hours", "has_more_pools", "has_more_services", "has_more_faqs"]:
            collected_data[field_name] = request.answer
    
    # Get next step with dynamic branching
    next_step, question_data, dynamic_question = get_next_step_and_question(
        current_step, request.answer, collected_data
    )
    
    # Check if interview is complete
    if next_step == InterviewStep.COMPLETE or current_step == InterviewStep.ANYTHING_ELSE:
        # Make sure to store the last answer
        if current_step == InterviewStep.ANYTHING_ELSE:
            collected_data["anything_else"] = request.answer
        return InterviewResponse(
            current_step=InterviewStep.COMPLETE.value,
            question="Great! I have all the information I need. Click 'Generate Prompt' to create your chatbot prompt.",
            question_type="complete",
            choices=None,
            collected_data=collected_data,
            is_complete=True,
            progress=100,
        )
    
    # Calculate progress based on main steps only
    main_step_count = len([s for s in STEP_ORDER if s not in LOOP_STEPS])
    if next_step in STEP_ORDER:
        # Count how many main steps we've completed
        next_index = STEP_ORDER.index(next_step)
        completed_main_steps = len([s for s in STEP_ORDER[:next_index] if s not in LOOP_STEPS])
        progress = int((completed_main_steps / main_step_count) * 100)
    else:
        # Loop step - estimate progress
        progress = int((len([k for k in collected_data.keys() if not k.startswith("_")]) / 20) * 100)
        progress = min(progress, 95)
    
    # Use dynamic question if provided, otherwise use static question
    question = dynamic_question or question_data.get("question", "")
    
    return InterviewResponse(
        current_step=next_step.value,
        question=question,
        question_type=question_data.get("type", "text"),
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
- Never make up information about services, pricing, or policies
- Keep responses concise but thorough
- Ask ONE question at a time to keep the conversation natural

CRITICAL - Keep the conversation flowing:
- ALWAYS end your response with a question or invitation to continue the conversation
- Never give dead-end responses that leave the customer with nothing to respond to
- After answering, ask a relevant follow-up question to understand their needs better
- Examples of good endings:
  * "What age group would this be for?"
  * "Would you like me to tell you more about our class options?"
  * "Is there a particular day or time that works best for you?"
  * "What questions do you have about getting started?"
- The conversation should feel like a natural back-and-forth, not a FAQ lookup"""

    # Build business info section with multiple locations support
    business_info_parts = []
    if data.get("business_name"):
        business_info_parts.append(f"Business Name: {data['business_name']}")
    if data.get("industry"):
        business_info_parts.append(f"Type of Business: {data['industry']}")
    
    # Handle multiple locations
    locations = data.get("locations", [])
    if locations and len(locations) > 1:
        business_info_parts.append("Locations:")
        for i, loc in enumerate(locations, 1):
            if loc:
                business_info_parts.append(f"  {i}) {loc}")
    elif data.get("location"):
        business_info_parts.append(f"Location: {data['location']}")
    
    if data.get("phone_number"):
        business_info_parts.append(f"Phone: {data['phone_number']}")
    if data.get("website_url"):
        business_info_parts.append(f"Website: {data['website_url']}")
    
    # Handle business hours with pool-specific hours
    if data.get("business_hours"):
        business_info_parts.append(f"Business Hours: {data['business_hours']}")
    
    pool_hours = data.get("pool_hours", [])
    if pool_hours:
        business_info_parts.append("\nPool Hours:")
        for pool in pool_hours:
            if pool.get("name") and pool.get("hours"):
                business_info_parts.append(f"  - {pool['name']}: {pool['hours']}")
    
    business_info_content = "\n".join(business_info_parts)

    # Build classes section with registration URLs
    classes_content = ""
    classes = data.get("classes", [])
    if classes:
        classes_parts = ["CLASSES & PROGRAMS:"]
        for cls in classes:
            if cls.get("name"):
                if cls.get("url"):
                    classes_parts.append(f"- {cls['name']}: Register at {cls['url']}")
                else:
                    classes_parts.append(f"- {cls['name']}")
        classes_content = "\n".join(classes_parts)

    # Build services section with sales pitches
    services_content = ""
    services_list = data.get("services_list", [])
    if services_list:
        services_parts = ["SERVICES & PRODUCTS:"]
        for svc in services_list:
            if svc.get("name"):
                services_parts.append(f"\n{svc['name']}:")
                if svc.get("pitch"):
                    services_parts.append(f"  {svc['pitch']}")
        services_content = "\n".join(services_parts)
    
    if data.get("pricing"):
        if services_content:
            services_content += f"\n\nPRICING:\n{data['pricing']}"
        else:
            services_content = f"PRICING:\n{data['pricing']}"

    # Build FAQ section from structured FAQs
    faq_content = ""
    faqs = data.get("faqs", [])
    if faqs:
        faq_parts = ["FREQUENTLY ASKED QUESTIONS:"]
        for faq in faqs:
            if faq.get("question") and faq.get("answer"):
                faq_parts.append(f"\nQ: {faq['question']}")
                faq_parts.append(f"A: {faq['answer']}")
        faq_content = "\n".join(faq_parts)

    # Build policies section from individual policy fields
    policies_content = ""
    policies_parts = []
    if data.get("cancellation_policy"):
        policies_parts.append(f"Cancellation Policy: {data['cancellation_policy']}")
    if data.get("refund_policy"):
        policies_parts.append(f"Refund Policy: {data['refund_policy']}")
    if data.get("booking_requirements"):
        policies_parts.append(f"Booking Requirements: {data['booking_requirements']}")
    if data.get("other_policies"):
        policies_parts.append(f"Other Policies: {data['other_policies']}")
    if policies_parts:
        policies_content = "POLICIES:\n" + "\n".join(policies_parts)
    
    # Build requirements section from individual requirement fields
    requirements_content = ""
    requirements_parts = []
    if data.get("age_requirements"):
        requirements_parts.append(f"Age Requirements: {data['age_requirements']}")
    if data.get("equipment_needed"):
        requirements_parts.append(f"Equipment/Items to Bring: {data['equipment_needed']}")
    if data.get("prerequisites"):
        requirements_parts.append(f"Prerequisites: {data['prerequisites']}")
    if data.get("other_requirements"):
        requirements_parts.append(f"Other Requirements: {data['other_requirements']}")
    if requirements_parts:
        requirements_content = "REQUIREMENTS:\n" + "\n".join(requirements_parts)

    # Build additional instructions
    additional_content = ""
    if data.get("anything_else"):
        additional_content = f"Additional Instructions:\n{data['anything_else']}"

    # Lead capture instructions - non-pushy, natural approach
    lead_capture_content = """CONTACT INFORMATION COLLECTION:

Goal: Collect customer's name and email/phone naturally during conversation.

CRITICAL RULE - NO EMAIL COMMUNICATION:
- NEVER offer to email or send information to the customer
- NEVER say "I can email you..." or "Would you like me to send you..."
- Instead, direct customers to URLs where they can find information
- If a registration URL exists, share it directly: "You can register at [URL]"
- If asked for schedules/details, share any URL you have or offer to have someone call them

Guidelines:
- Be helpful FIRST, collect info SECOND - always answer their question before asking for contact info
- Don't be pushy - if they don't want to share, that's okay
- Ask for ONE piece of info at a time (don't ask for name, email, AND phone all at once)
- Make it feel conversational, not like filling out a form
- Share URLs and links when available instead of offering to email

Progressive Collection Pattern:
1. First, try to get email OR phone (whichever feels more natural)
   - "I'd be happy to have someone follow up with you. What's the best way to reach you?"
   - "Would you like us to give you a call to discuss this further?"
2. If they provide email, you can optionally ask for phone:
   - "Thanks! In case we need to reach you quickly, would you like to share a phone number too?"
3. After getting contact info, ask for their name once:
   - "And may I ask who I'm speaking with today?"

Examples of GOOD (natural) approaches:
- "You can find all our class schedules at [website URL]. Would you like someone to call you to help pick the right one?"
- "I'd love to help you find the right option. Can I have someone give you a call?"
- "Here's the link to sign up: [URL]. If you have questions, I can have our team reach out!"

Examples of BAD (avoid these):
- "I can email you our schedule" - DON'T offer to email
- "Would you like me to send that to your email?" - DON'T offer to send emails
- "Before I answer, I'll need your name, email, and phone number." - DON'T be pushy
- "Please provide your contact information to continue." - DON'T block conversation

Remember: One piece of contact info is acceptable. Name + (email or phone) is ideal. Never make them feel pressured. Direct them to URLs for information rather than offering to email."""

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
    
    order_idx = 2
    
    if classes_content:
        sections_data.append({"section_key": "classes", "scope": "business_info", "content": classes_content, "order": order_idx})
        order_idx += 1
    
    if services_content:
        sections_data.append({"section_key": "services", "scope": "business_info", "content": services_content, "order": order_idx})
        order_idx += 1
    
    if faq_content:
        sections_data.append({"section_key": "faq", "scope": "faq", "content": faq_content, "order": order_idx})
        order_idx += 1
    
    if policies_content:
        sections_data.append({"section_key": "policies", "scope": "custom", "content": policies_content, "order": order_idx})
        order_idx += 1
    
    if requirements_content:
        sections_data.append({"section_key": "requirements", "scope": "custom", "content": requirements_content, "order": order_idx})
        order_idx += 1
    
    sections_data.append({"section_key": "lead_capture", "scope": "custom", "content": lead_capture_content, "order": order_idx})
    order_idx += 1
    
    if additional_content:
        sections_data.append({"section_key": "additional", "scope": "custom", "content": additional_content, "order": order_idx})
    
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
