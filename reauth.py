"""Run this once to refresh oauth_token.json when the refresh token expires.

Requires client_secret.json (Desktop app type) downloaded from Google Cloud Console:
  APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app → Download JSON
  Save as lyric360_backend/client_secret.json
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

TOKEN_FILE = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "oauth_token.json")
CLIENT_SECRET_FILE = "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/photoslibrary",
    "https://www.googleapis.com/auth/photoslibrary.sharing",
]

creds = None
if os.path.exists(TOKEN_FILE):
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        creds = flow.run_local_server(port=0)

with open(TOKEN_FILE, "w") as f:
    f.write(creds.to_json())

print(f"✓ Saved new token to {TOKEN_FILE}")
