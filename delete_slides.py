import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/drive'
]

OAUTH_CREDENTIALS_FILE = 'oauth_token.json'
TOKEN_FILE = 'oauth_token.json'


def get_credentials():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
        print(f"Token saved to {TOKEN_FILE}")

    return creds


def extract_presentation_id(slides_link):
    """Extract presentation ID from a Google Slides link."""
    import re
    patterns = [
        r'/presentation/d/([a-zA-Z0-9_-]+)',
        r'/d/([a-zA-Z0-9_-]+)',
        r'[?&]id=([a-zA-Z0-9_-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, slides_link)
        if match:
            return match.group(1)
    # Assume raw presentation ID if no pattern matches
    return slides_link.strip()


def delete_presentations(slides_links):
    creds = get_credentials()
    slides_service = build('slides', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)

    results = {'success': [], 'failed': []}

    for link in slides_links:
        presentation_id = extract_presentation_id(link)
        try:
            # Fetch presentation title via Slides API before deleting
            presentation = slides_service.presentations().get(
                presentationId=presentation_id,
                fields='title'
            ).execute()
            title = presentation.get('title', presentation_id)

            # Delete via Drive API (Slides API has no delete endpoint)
            drive_service.files().delete(fileId=presentation_id).execute()

            print(f"✓ Deleted: \"{title}\" ({presentation_id})")
            results['success'].append(presentation_id)

        except HttpError as e:
            print(f"✗ Failed [{presentation_id}]: HTTP {e.status_code} – {e.reason}")
            results['failed'].append(presentation_id)
        except Exception as e:
            print(f"✗ Failed [{presentation_id}]: {e}")
            results['failed'].append(presentation_id)

    print(f"\nDone. {len(results['success'])} deleted, {len(results['failed'])} failed.")
    return results


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python delete_slides.py <slides_link_or_id> [<slides_link_or_id> ...]")
        print("Example: python delete_slides.py https://docs.google.com/presentation/d/ABC123/edit")
        sys.exit(1)

    delete_presentations(sys.argv[1:])