"""Run this once to refresh oauth_token.json when the refresh token expires."""
import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow

TOKEN_FILE = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "oauth_token.json")
SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
]

with open(TOKEN_FILE) as f:
    existing = json.load(f)

client_config = {
    "installed": {
        "client_id": existing["client_id"],
        "client_secret": existing["client_secret"],
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": existing["token_uri"],
    }
}

flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
creds = flow.run_local_server(port=0)

with open(TOKEN_FILE, "w") as f:
    f.write(creds.to_json())

print(f"✓ Saved new token to {TOKEN_FILE}")
