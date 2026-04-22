import logging
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

VIDEO_OUTPUT_FOLDER_ID = os.getenv("VIDEO_OUTPUT_FOLDER_ID", "")
OAUTH_TOKEN_FILE = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "oauth_token.json")
SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
]


def _get_drive():
    creds = Credentials.from_authorized_user_file(OAUTH_TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(OAUTH_TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            logger.warning("Token refresh failed, proceeding with existing token: %s", e)
    return build("drive", "v3", credentials=creds)


def create_session_folder(folder_name: str) -> str:
    """Create a Drive folder for a session and return its ID."""
    drive = _get_drive()
    parent = VIDEO_OUTPUT_FOLDER_ID or "root"
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent],
    }
    folder = drive.files().create(
        body=metadata,
        fields="id",
        supportsAllDrives=True,
    ).execute()
    folder_id = folder["id"]
    logger.info("Created session folder: %s (%s)", folder_name, folder_id)
    return folder_id


def delete_drive_file(file_id: str) -> None:
    """Delete a file from Google Drive by its ID. Silently ignores 404."""
    drive = _get_drive()
    try:
        drive.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        logger.info("Deleted Drive file: %s", file_id)
    except Exception as e:
        logger.warning("Could not delete Drive file %s: %s", file_id, e)


def upload_video_to_drive(file_path: str, filename: str, folder_id: str | None = None) -> str:
    """Upload a video file to Google Drive, return the webViewLink."""
    drive = _get_drive()

    parent = folder_id or VIDEO_OUTPUT_FOLDER_ID or "root"
    file_metadata: dict = {"name": filename, "parents": [parent]}

    media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)
    result = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id,webViewLink",
        supportsAllDrives=True,
    ).execute()

    url = result.get("webViewLink") or f"https://drive.google.com/file/d/{result['id']}/view"
    logger.info("Uploaded video to Drive: %s → %s", filename, url)
    return url