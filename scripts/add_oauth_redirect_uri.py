#!/usr/bin/env python3
"""Add redirect URI to OAuth client using Google API."""

import subprocess
import sys
import json

def get_access_token():
    """Get access token from gcloud."""
    result = subprocess.run(
        ['gcloud', 'auth', 'print-access-token'],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Error getting access token: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def main():
    project_id = "chatbots-466618"
    client_id = "900139201687-mtr05hsjpoj2tpjtrrvdbm70ppso78t0.apps.googleusercontent.com"
    redirect_uri = "https://chattercheatah-900139201687.us-central1.run.app/api/v1/email/oauth/callback"
    
    access_token = get_access_token()
    
    # Use the Google Cloud Identity Platform API
    import urllib.request
    import urllib.parse
    
    # First get the current client config
    get_url = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{project_id}/oauthIdpConfig/{client_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        # Try to get current config
        req = urllib.request.Request(get_url, headers=headers)
        with urllib.request.urlopen(req) as response:
            config = json.loads(response.read())
            print(f"Current config: {json.dumps(config, indent=2)}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("Note: OAuth client management via API may require different endpoints.")
            print("\nPlease add the redirect URI manually:")
            print(f"1. Go to: https://console.cloud.google.com/apis/credentials?project={project_id}")
            print(f"2. Click on 'Chatter Cheetah Web Client'")
            print(f"3. Scroll to 'Authorized redirect URIs'")
            print(f"4. Click '+ Add URI'")
            print(f"5. Add: {redirect_uri}")
            print(f"6. Click 'Save'")
            sys.exit(0)
        else:
            print(f"Error: {e.code} - {e.read().decode()}")
            sys.exit(1)

if __name__ == "__main__":
    main()

