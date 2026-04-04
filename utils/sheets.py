import logging
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# Use the same scopes as slides.py — the broad "drive" scope already grants
# read access to the Sheets API v4, so no extra scope is needed.
SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
]

OAUTH_TOKEN_FILE = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "oauth_token.json")
DEFAULT_SPREADSHEET_ID = os.getenv("SYNC_SPREADSHEET_ID", "")


def _get_sheets_service():
    creds = Credentials.from_authorized_user_file(OAUTH_TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        logger.info("Refreshing OAuth token for Sheets API...")
        creds.refresh(Request())
        with open(OAUTH_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def read_sheet_rows(sheet_name: str, spreadsheet_id: str | None = None) -> list[dict]:
    """
    Read all data rows from a Google Sheet.

    Expected column order (0-indexed):
      0: Tên file gốc
      1: Link Sheet
      2: Tên bài hát chuẩn   ← used as the song title / lookup key
      3: Tác giả
      4: Năm sáng tác
      5: Lời bài hát
      6: Link Lyric           ← slide_drive_url
      7: Step
      8: Status

    Returns a list of dicts (header row skipped). Rows with an empty
    "Tên bài hát chuẩn" are ignored.
    """
    sid = spreadsheet_id or DEFAULT_SPREADSHEET_ID
    if not sid:
        raise ValueError("SYNC_SPREADSHEET_ID env var is not configured")

    svc = _get_sheets_service()
    logger.info("Reading sheet '%s' from spreadsheet %s", sheet_name, sid)
    result = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=sid, range=f"{sheet_name}!A:I")
        .execute()
    )

    values = result.get("values", [])
    if len(values) < 2:
        return []

    rows = []
    for i, row in enumerate(values[1:], start=2):  # row 1 = header
        while len(row) < 9:
            row.append("")
        title = row[2].strip()
        if not title:
            continue
        rows.append(
            {
                "row_number": i,
                "original_file": row[0].strip() or None,
                "sheet_url": row[1].strip() or None,
                "song_title": title,
                "author": row[3].strip() or None,
                "year": row[4].strip() or None,
                "lyrics": row[5].strip() or None,
                "lyric_slide_url": row[6].strip() or None,
                "step": row[7].strip() or None,
                "status": row[8].strip() or None,
            }
        )
    logger.info("Read %d rows from sheet '%s'", len(rows), sheet_name)
    return rows