"""
Google Photos Library API helper.

Uses the same oauth_token.json as slides.py — no separate auth needed.
The token must include photoslibrary.readonly scope (already added to reauth.py SCOPES).

One-time setup:
  1. Delete oauth_token.json
  2. Re-authorize via: python reauth.py  (sign in as sacmau1971@gmail.com)
  3. Done — works forever, auto-refreshes silently.

Matching logic:
  Google Photos `creationTime` = when recording STARTED (most phones).
  Best match = the video with the latest creationTime <= song.actual_start.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import requests as http
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/photoslibrary",
    "https://www.googleapis.com/auth/photoslibrary.sharing",
]
PHOTOS_API = "https://photoslibrary.googleapis.com/v1"
OAUTH_TOKEN_FILE = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "oauth_token.json")


def _get_creds() -> Credentials:
    creds = Credentials.from_authorized_user_file(OAUTH_TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(OAUTH_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


# ── Photos API ───────────────────────────────────────────────────────────────

def list_videos_on_date(session_date_str: str) -> list[dict]:
    """Return all video media items on the given date (YYYY-MM-DD)."""
    creds = _get_creds()
    headers = {"Authorization": f"Bearer {creds.token}"}
    year, month, day = session_date_str.split("-")
    payload: dict = {
        "filters": {
            "dateFilter": {"dates": [{"year": int(year), "month": int(month), "day": int(day)}]},
            "mediaTypeFilter": {"mediaTypes": ["VIDEO"]},
        },
        "pageSize": 100,
    }

    items = []
    page_token = None
    while True:
        if page_token:
            payload["pageToken"] = page_token
        r = http.post(f"{PHOTOS_API}/mediaItems:search", json=payload, headers=headers, timeout=15)
        if not r.ok:
            logger.error("Photos API error %s: %s", r.status_code, r.text)
            r.raise_for_status()
        data = r.json()
        for item in data.get("mediaItems", []):
            raw = item.get("mediaMetadata", {}).get("creationTime", "")
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                dt = None
            items.append({
                "id": item["id"],
                "productUrl": item.get("productUrl", ""),
                "creationTime": dt,
            })
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    items.sort(key=lambda x: x["creationTime"] or datetime.min.replace(tzinfo=timezone.utc))
    logger.info("Photos: found %d videos on %s", len(items), session_date_str)
    return items


def find_video_for_song(
    videos: list[dict],
    actual_start: datetime,
    actual_end: datetime,
) -> Optional[str]:
    """Return productUrl of the best-matching video, or None."""
    def as_utc(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    start = as_utc(actual_start)
    end = as_utc(actual_end)

    candidates = [v for v in videos if v["creationTime"] and as_utc(v["creationTime"]) <= end]
    if not candidates:
        return None

    before = [v for v in candidates if as_utc(v["creationTime"]) <= start]
    pool = before if before else candidates
    return max(pool, key=lambda v: v["creationTime"])["productUrl"]
