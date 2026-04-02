import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

SCOPES = [
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/drive'
]

OAUTH_CREDENTIALS_FILE = 'oauth_token.json'
TOKEN_FILE = 'oauth_token.json'
PARENT_FOLDER_ID = '1EvpjdEjowXTU9SaVRZTPo9Bok25akpjd'


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


def upload_file(file_path):
    creds = get_credentials()
    drive_service = build('drive', 'v3', credentials=creds)

    try:
        file_name = os.path.basename(file_path)
        file_metadata = {
            'name': file_name,
            'parents': [PARENT_FOLDER_ID]
        }

        media = MediaFileUpload(file_path, resumable=True)

        result = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()

        print(f"Success! File uploaded.")
        print(f"  ID:   {result.get('id')}")
        print(f"  Name: {result.get('name')}")
        print(f"  URL:  {result.get('webViewLink')}")

        return result.get('id')

    except HttpError as e:
        print(f"HttpError {e.status_code}: {e.reason}")
        print(f"Details: {e.error_details}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python upload_file_test.py <file_path>")
        sys.exit(1)
    upload_file(sys.argv[1])
