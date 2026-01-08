"""Interactive script to onboard a new tenant with admin user, business profile, and prompts."""

import asyncio
import os
import sys
import re
import getpass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.persistence.database import AsyncSessionLocal
from app.persistence.repositories.tenant_repository import TenantRepository
from app.persistence.repositories.user_repository import UserRepository
from app.persistence.repositories.business_profile_repository import BusinessProfileRepository
from app.persistence.repositories.prompt_repository import PromptRepository
from app.domain.services.prompt_service import PromptService
from app.persistence.models.tenant import User
from app.persistence.models.prompt import PromptBundle, PromptSection, PromptStatus, SectionScope
from app.core.password import hash_password


def validate_subdomain(subdomain: str) -> bool:
    """Validate subdomain format."""
    if not subdomain:
        return False
    # Allow alphanumeric and hyphens, must start with letter/number
    pattern = r'^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$'
    return bool(re.match(pattern, subdomain)) and len(subdomain) <= 100


def validate_email(email: str) -> bool:
    """Basic email validation."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def get_password_input(prompt: str = "Password: ") -> str:
    """Get password input with confirmation."""
    while True:
        password = getpass.getpass(prompt)
        if len(password) < 8:
            print("Password must be at least 8 characters long.")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match. Please try again.")
            continue
        return password


def get_optional_input(prompt: str, default: str = "") -> str:
    """Get optional input with default."""
    response = input(f"{prompt} (press Enter to skip): ").strip()
    return response if response else default


async def onboard_tenant():
    """Interactive tenant onboarding process."""
    print("=" * 70)
    print("TENANT ONBOARDING - Interactive Setup")
    print("=" * 70)
    print()
    
    async with AsyncSessionLocal() as db:
        try:
            # Initialize repositories
            tenant_repo = TenantRepository(db)
            user_repo = UserRepository(db)
            profile_repo = BusinessProfileRepository(db)
            prompt_repo = PromptRepository(db)
            prompt_service = PromptService(db)
            
            # Step 1: Collect tenant information
            print("STEP 1: Tenant Information")
            print("-" * 70)
            
            tenant_name = input("Tenant name: ").strip()
            if not tenant_name:
                print("❌ Tenant name is required.")
                return
            
            subdomain = input("Subdomain (alphanumeric, hyphens allowed): ").strip().lower()
            if not subdomain:
                print("❌ Subdomain is required.")
                return
            
            if not validate_subdomain(subdomain):
                print("❌ Invalid subdomain format. Use alphanumeric characters and hyphens only.")
                return
            
            # Check if subdomain already exists
            existing_tenant = await tenant_repo.get_by_subdomain(subdomain)
            if existing_tenant:
                print(f"❌ Subdomain '{subdomain}' is already taken (Tenant ID: {existing_tenant.id})")
                return
            
            # Step 2: Collect admin user information
            print()
            print("STEP 2: Admin User Information")
            print("-" * 70)
            
            admin_email = input("Admin email: ").strip().lower()
            if not admin_email:
                print("❌ Admin email is required.")
                return
            
            if not validate_email(admin_email):
                print("❌ Invalid email format.")
                return
            
            # Check if email already exists
            existing_user = await user_repo.get_by_email(admin_email)
            if existing_user:
                print(f"❌ Email '{admin_email}' is already registered (User ID: {existing_user.id})")
                return
            
            admin_password = get_password_input("Admin password (min 8 chars): ")
            
            # Step 3: Create tenant
            print()
            print("STEP 3: Creating Tenant")
            print("-" * 70)
            
            tenant = await tenant_repo.create(
                tenant_id=None,
                name=tenant_name,
                subdomain=subdomain,
                is_active=True,
            )
            print(f"✓ Created tenant: {tenant.name} (ID: {tenant.id})")
            
            # Step 4: Create admin user
            print()
            print("STEP 4: Creating Admin User")
            print("-" * 70)
            
            admin_user = User(
                tenant_id=tenant.id,
                email=admin_email,
                hashed_password=hash_password(admin_password),
                role="tenant_admin",
            )
            db.add(admin_user)
            await db.commit()
            await db.refresh(admin_user)
            print(f"✓ Created admin user: {admin_user.email}")
            
            # Step 5: Optional business profile
            print()
            print("STEP 5: Business Profile (Optional)")
            print("-" * 70)
            setup_profile = input("Set up business profile now? (y/n): ").strip().lower() == 'y'
            
            if setup_profile:
                business_name = get_optional_input("Business name", tenant_name)
                website_url = get_optional_input("Website URL")
                phone_number = get_optional_input("Phone number (e.g., +15555550123)")
                business_email = get_optional_input("Business email", admin_email)
                twilio_phone = get_optional_input("Twilio phone number (optional)")
                
                # Create profile
                profile = await profile_repo.create_for_tenant(tenant.id)
                
                # Update with provided values
                await profile_repo.update_profile(
                    tenant_id=tenant.id,
                    business_name=business_name if business_name else None,
                    website_url=website_url if website_url else None,
                    phone_number=phone_number if phone_number else None,
                    email=business_email if business_email else None,
                    twilio_phone=twilio_phone if twilio_phone else None,
                )
                print(f"✓ Created business profile")
            else:
                print("Skipped business profile setup")
            
            # Step 6: Optional prompt setup
            print()
            print("STEP 6: Prompt Bundle Setup (Optional)")
            print("-" * 70)
            setup_prompt = input("Set up prompt bundle now? (y/n): ").strip().lower() == 'y'
            
            if setup_prompt:
                prompt_name = get_optional_input("Prompt bundle name", f"{tenant_name} Prompt Bundle")
                
                print("\nEnter business description and instructions:")
                print("(This will be used as the main business_info section)")
                business_prompt = input("Business prompt: ").strip()
                
                if not business_prompt:
                    print("⚠️  No business prompt provided, skipping prompt setup")
                else:
                    # Create prompt bundle
                    bundle = await prompt_repo.create(
                        tenant_id=tenant.id,
                        name=prompt_name,
                        version="1.0.0",
                        status=PromptStatus.DRAFT.value,
                        is_active=False,
                    )
                    
                    # Create sections
                    sections = []
                    
                    # System section (basic)
                    sections.append(PromptSection(
                        bundle_id=bundle.id,
                        section_key="system",
                        scope=SectionScope.SYSTEM.value,
                        content="You are a helpful customer service assistant. Be friendly, professional, and concise.",
                        order=0,
                    ))
                    
                    # Business info section
                    sections.append(PromptSection(
                        bundle_id=bundle.id,
                        section_key="business_info",
                        scope=SectionScope.BUSINESS_INFO.value,
                        content=business_prompt,
                        order=1,
                    ))
                    
                    # Optional FAQ
                    print()
                    faq = get_optional_input("FAQ content (optional): ")
                    if faq:
                        sections.append(PromptSection(
                            bundle_id=bundle.id,
                            section_key="faq",
                            scope=SectionScope.FAQ.value,
                            content=f"Frequently Asked Questions:\n\n{faq}",
                            order=2,
                        ))
                    
                    # Optional rules
                    print()
                    rules = get_optional_input("Rules and guidelines (optional): ")
                    if rules:
                        sections.append(PromptSection(
                            bundle_id=bundle.id,
                            section_key="rules",
                            scope=SectionScope.CUSTOM.value,
                            content=f"Rules and Guidelines:\n\n{rules}",
                            order=3,
                        ))
                    
                    # Add all sections
                    for section in sections:
                        db.add(section)
                    
                    await db.commit()
                    
                    # Publish to production
                    published_bundle = await prompt_service.publish_bundle(tenant.id, bundle.id)
                    if published_bundle:
                        print(f"✓ Created and published prompt bundle: {published_bundle.name}")
                    else:
                        print("⚠️  Created prompt bundle but failed to publish")
            else:
                print("Skipped prompt setup")
            
            # Step 7: Summary
            print()
            print("=" * 70)
            print("ONBOARDING COMPLETE!")
            print("=" * 70)
            print()
            print(f"Tenant ID: {tenant.id}")
            print(f"Tenant Name: {tenant.name}")
            print(f"Subdomain: {tenant.subdomain}")
            print()
            print("Admin User:")
            print(f"  Email: {admin_user.email}")
            print(f"  Password: [hidden]")
            print()
            print("Next Steps:")
            print()
            print("1. Login and get JWT token:")
            print(f"   POST /api/v1/auth/login")
            print(f"   Body: {{'email': '{admin_user.email}', 'password': '<your-password>'}}")
            print()
            print("2. Configure integrations (use JWT token in Authorization header):")
            print()
            print("   SMS/Voice Configuration (Telnyx):")
            print("   - POST /api/v1/admin/telephony/config")
            print("     Required fields:")
            print("       • provider: 'telnyx'")
            print("       • telnyx_api_key: API key from Telnyx portal")
            print("       • telnyx_phone_number: SMS number (+1XXXXXXXXXX)")
            print("       • telnyx_messaging_profile_id: From Telnyx messaging profile")
            print("       • telnyx_connection_id: From Telnyx TeXML app (for voice)")
            print("       • voice_phone_number: Voice number (can be same as SMS)")
            print("       • sms_enabled: true")
            print("       • voice_enabled: true")
            print()
            print("   ⚠️  IMPORTANT: 10DLC COMPLIANCE (US SMS)")
            print("   Before SMS will work to major carriers (Verizon, AT&T, T-Mobile):")
            print("   1. Go to Telnyx Portal → Messaging → 10DLC → Campaigns")
            print("   2. Create/select a 10DLC campaign for the tenant")
            print("   3. Add the tenant's phone number to the campaign")
            print("   4. Wait for 'Assigned' status (can take 24-48 hours)")
            print("   Without 10DLC registration, SMS will fail with error 40010")
            print()
            print("   Voice Configuration:")
            print("   - PUT /api/v1/voice/settings")
            print("     (Configure greeting, handoff mode, escalation rules)")
            print()
            print("   Email Configuration:")
            print("   - POST /api/v1/email/oauth/start")
            print("     (Initiates Gmail OAuth flow)")
            print()
            print("3. Test the chat:")
            print("   POST /api/v1/chat")
            print("   Body: {{'message': 'Hello', 'conversation_id': null}}")
            print()
            print("For detailed setup instructions, see: docs/tenant_onboarding.md")
            print()
            
        except Exception as e:
            print(f"\n❌ Error during onboarding: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(onboard_tenant())

