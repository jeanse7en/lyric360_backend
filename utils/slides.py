import logging
import math
import os
import traceback

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/photoslibrary",
    "https://www.googleapis.com/auth/photoslibrary.sharing",
]
OAUTH_TOKEN_FILE = os.getenv("GOOGLE_OAUTH_TOKEN_FILE", "oauth_token.json")
OUTPUT_FOLDER_ID = os.getenv("SLIDES_OUTPUT_FOLDER_ID", "")

# Standard Google Slides dimensions (720pt x 405pt)
BOX_WIDTH_PT = 330
LYRICS_TOP_PT = 75      # below title + author boxes
MAX_BOX_HEIGHT_PT = 310  # 405 - 75 - 20 bottom margin


def _get_services():
    logger.info("Loading OAuth token from: %s", os.path.abspath(OAUTH_TOKEN_FILE))
    creds = Credentials.from_authorized_user_file(OAUTH_TOKEN_FILE, SCOPES)

    if creds.expired and creds.refresh_token:
        logger.info("Token expired, refreshing...")
        creds.refresh(Request())
        with open(OAUTH_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        logger.info("Token refreshed and saved.")

    slides = build("slides", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return slides, drive


def _pt(value: float) -> int:
    """Convert points to EMUs (1pt = 12700 EMU)."""
    return int(value * 12700)


def _rgb(hex_color: str) -> dict:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return {"red": r / 255, "green": g / 255, "blue": b / 255}


def _get_physical_lines(text: str, font_size: int, box_width: float) -> int:
    if not text:
        return 0
    char_width = font_size * 0.55
    chars_per_line = max(1, int(box_width / char_width))
    total = 0
    for line in text.split("\n"):
        total += 1 if len(line) == 0 else math.ceil(len(line) / chars_per_line)
    return total


def _calc_font_size(left: str, right: str, start: int = 28) -> int:
    font_size = start
    while font_size >= 10:
        left_lines = _get_physical_lines(left, font_size, BOX_WIDTH_PT)
        right_lines = _get_physical_lines(right, font_size, BOX_WIDTH_PT)
        if max(left_lines, right_lines) * (font_size * 1.3) <= MAX_BOX_HEIGHT_PT:
            break
        font_size -= 1
    return font_size


def _split_lyrics(lyrics: str) -> tuple[str, str]:
    stanzas = lyrics.strip().split("\n\n")
    mid = math.ceil(len(stanzas) / 2)
    return "\n\n".join(stanzas[:mid]), "\n\n".join(stanzas[mid:])


def _textbox_requests(obj_id: str, text: str, slide_id: str,
                      left: float, top: float, width: float, height: float) -> list:
    return [
        {
            "createShape": {
                "objectId": obj_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": _pt(width), "unit": "EMU"},
                        "height": {"magnitude": _pt(height), "unit": "EMU"},
                    },
                    "transform": {
                        "scaleX": 1, "scaleY": 1,
                        "translateX": _pt(left), "translateY": _pt(top),
                        "unit": "EMU",
                    },
                },
            }
        },
        {
            "insertText": {
                "objectId": obj_id,
                "text": text,
                "insertionIndex": 0,
            }
        },
    ]


def create_lyric_slide(title: str, author: str | None, lyrics: str) -> str:
    """
    Create a Google Slides presentation from song lyrics.

    Layout:
    - Black background
    - Title (uppercase, red, bold, 26pt, centered)
    - Author subtitle (italic, gray, 14pt, centered)
    - Lyrics split into left/right columns (yellow, bold, auto font size)

    Returns the presentation URL.
    """
    logger.info("create_lyric_slide: title=%r author=%r lyrics_len=%d", title, author, len(lyrics))
    slides_svc, drive_svc = _get_services()

    final_title = title.upper()
    final_author = f"Sáng tác: {author}" if author else "Sáng tác: Đang cập nhật"
    left_text, right_text = _split_lyrics(lyrics)
    font_size = _calc_font_size(left_text, right_text)
    logger.info("Font size calculated: %d | left_len=%d right_len=%d", font_size, len(left_text), len(right_text))

    # Create presentation
    logger.info("Creating presentation via Slides API...")
    pres = slides_svc.presentations().create(body={"title": title}).execute()
    pres_id = pres["presentationId"]
    slide_id = pres["slides"][0]["objectId"]
    logger.info("Presentation created: %s | slide_id=%s", pres_id, slide_id)

    # IDs of default elements to delete
    existing_ids = [e["objectId"] for e in pres["slides"][0].get("pageElements", [])]

    requests = []

    # Delete default elements
    for eid in existing_ids:
        requests.append({"deleteObject": {"objectId": eid}})

    # Black background
    requests.append({
        "updatePageProperties": {
            "objectId": slide_id,
            "pageProperties": {
                "pageBackgroundFill": {
                    "solidFill": {"color": {"rgbColor": _rgb("#000000")}}
                }
            },
            "fields": "pageBackgroundFill",
        }
    })

    # Title box (y=10, h=40)
    requests += _textbox_requests("title_box", final_title, slide_id, 20, 10, 680, 40)
    requests += [
        {
            "updateTextStyle": {
                "objectId": "title_box",
                "textRange": {"type": "ALL"},
                "style": {
                    "fontSize": {"magnitude": 26, "unit": "PT"},
                    "bold": True,
                    "foregroundColor": {"opaqueColor": {"rgbColor": _rgb("#FF3333")}},
                },
                "fields": "fontSize,bold,foregroundColor",
            }
        },
        {
            "updateParagraphStyle": {
                "objectId": "title_box",
                "textRange": {"type": "ALL"},
                "style": {"alignment": "CENTER"},
                "fields": "alignment",
            }
        },
    ]

    # Author box (y=45, h=25)
    requests += _textbox_requests("author_box", final_author, slide_id, 20, 45, 680, 25)
    requests += [
        {
            "updateTextStyle": {
                "objectId": "author_box",
                "textRange": {"type": "ALL"},
                "style": {
                    "fontSize": {"magnitude": 14, "unit": "PT"},
                    "italic": True,
                    "foregroundColor": {"opaqueColor": {"rgbColor": _rgb("#CCCCCC")}},
                },
                "fields": "fontSize,italic,foregroundColor",
            }
        },
        {
            "updateParagraphStyle": {
                "objectId": "author_box",
                "textRange": {"type": "ALL"},
                "style": {"alignment": "CENTER"},
                "fields": "alignment",
            }
        },
    ]

    # Left lyrics column
    if left_text:
        requests += _textbox_requests(
            "left_box", left_text, slide_id,
            20, LYRICS_TOP_PT, BOX_WIDTH_PT, MAX_BOX_HEIGHT_PT,
        )
        requests.append({
            "updateTextStyle": {
                "objectId": "left_box",
                "textRange": {"type": "ALL"},
                "style": {
                    "fontSize": {"magnitude": font_size, "unit": "PT"},
                    "bold": True,
                    "foregroundColor": {"opaqueColor": {"rgbColor": _rgb("#FFFF00")}},
                },
                "fields": "fontSize,bold,foregroundColor",
            }
        })

    # Right lyrics column
    if right_text:
        requests += _textbox_requests(
            "right_box", right_text, slide_id,
            370, LYRICS_TOP_PT, BOX_WIDTH_PT, MAX_BOX_HEIGHT_PT,
        )
        requests.append({
            "updateTextStyle": {
                "objectId": "right_box",
                "textRange": {"type": "ALL"},
                "style": {
                    "fontSize": {"magnitude": font_size, "unit": "PT"},
                    "bold": True,
                    "foregroundColor": {"opaqueColor": {"rgbColor": _rgb("#FFFF00")}},
                },
                "fields": "fontSize,bold,foregroundColor",
            }
        })

    # Execute all formatting requests
    logger.info("Sending batchUpdate with %d requests...", len(requests))
    slides_svc.presentations().batchUpdate(
        presentationId=pres_id,
        body={"requests": requests},
    ).execute()
    logger.info("batchUpdate complete")

    # Move to output folder (Shared Drive) if configured
    if OUTPUT_FOLDER_ID:
        logger.info("Moving to output folder: %s", OUTPUT_FOLDER_ID)
        drive_svc.files().update(
            fileId=pres_id,
            addParents=OUTPUT_FOLDER_ID,
            removeParents="root",
            supportsAllDrives=True,
            fields="id,parents",
        ).execute()

    url = f"https://docs.google.com/presentation/d/{pres_id}/edit"
    logger.info("Done: %s", url)
    return url
