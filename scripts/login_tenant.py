"""Login script to obtain JWT token for a tenant.

Usage:
    uv run python scripts/login_tenant.py \
        --email "admin@tenant.com" \
        --password "password123" \
        [--api-base "http://localhost:8000" | "https://your-production-url.com"]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def login(email: str, password: str, api_base: str = "http://localhost:8000") -> dict | None:
    """Login and get JWT token using curl."""
    url = f"{api_base}/api/v1/auth/login"
    
    print(f"Logging in to: {url}")
    print(f"Email: {email}")
    print()
    
    payload = json.dumps({"email": email, "password": password})
    
    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-X", "POST",
                "-H", "Content-Type: application/json",
                "-d", payload,
                url
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print(f"❌ Error: curl command failed")
            print(f"   {result.stderr}")
            return None
        
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"❌ Error: Invalid JSON response")
            print(f"   Response: {result.stdout}")
            return None
        
        if "access_token" in data:
            print("✓ Login successful!")
            print()
            print("=" * 70)
            print("LOGIN RESPONSE")
            print("=" * 70)
            print()
            token_preview = data.get('access_token', 'N/A')[:50] + "..." if len(data.get('access_token', '')) > 50 else data.get('access_token', 'N/A')
            print(f"Access Token: {token_preview}")
            print(f"Tenant ID: {data.get('tenant_id', 'N/A')}")
            print(f"Role: {data.get('role', 'N/A')}")
            print(f"Email: {data.get('email', 'N/A')}")
            print(f"Is Global Admin: {data.get('is_global_admin', False)}")
            print()
            
            # Save token to file
            token_file = Path(__file__).parent.parent / ".auth_token"
            token_data = {
                "access_token": data.get("access_token"),
                "tenant_id": data.get("tenant_id"),
                "role": data.get("role"),
                "email": data.get("email"),
                "is_global_admin": data.get("is_global_admin"),
            }
            
            with open(token_file, "w") as f:
                json.dump(token_data, f, indent=2)
            
            print(f"✓ Token saved to: {token_file}")
            print()
            print("To use this token in API requests:")
            print(f'  export JWT_TOKEN="{data.get("access_token")}"')
            print()
            print("Or use in curl requests:")
            print(f'  curl -H "Authorization: Bearer {data.get("access_token")[:20]}..." ...')
            print()
            
            return data
        else:
            # Likely an error response
            print(f"❌ Login failed")
            error_msg = data.get('detail', result.stdout)
            print(f"   Error: {error_msg}")
            return None
            
    except subprocess.TimeoutExpired:
        print(f"❌ Error: Connection to {api_base} timed out")
        return None
    except FileNotFoundError:
        print("❌ Error: 'curl' command not found. Please install curl.")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def main():
    """Parse arguments and run login."""
    parser = argparse.ArgumentParser(
        description="Login to obtain JWT token for a tenant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local development server:
  uv run python scripts/login_tenant.py \\
      --email "admin@tenant.com" \\
      --password "password123"

  # Production server:
  uv run python scripts/login_tenant.py \\
      --email "admin@tenant.com" \\
      --password "password123" \\
      --api-base "https://chattercheatah-900139201687.us-central1.run.app"
        """
    )
    
    parser.add_argument("--email", required=True, help="Admin user email")
    parser.add_argument("--password", required=True, help="Admin user password")
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)"
    )
    
    args = parser.parse_args()
    
    login(args.email, args.password, args.api_base)


if __name__ == "__main__":
    main()

