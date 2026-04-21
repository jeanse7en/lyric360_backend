import logging
import os

from googleapiclient.http import MediaFileUpload

from utils.slides import _get_services

logger = logging.getLogger(__name__)

VIDEO_OUTPUT_FOLDER_ID = os.getenv("VIDEO_OUTPUT_FOLDER_ID", "")


def upload_video_to_drive(file_path: str, filename: str) -> str:
    """Upload a video file to Google Drive, return the webViewLink."""
    _, drive = _get_services()

    file_metadata: dict = {"name": filename}
    if VIDEO_OUTPUT_FOLDER_ID:
        file_metadata["parents"] = [VIDEO_OUTPUT_FOLDER_ID]

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
