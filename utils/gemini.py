import json
import os
import re
import httpx

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


def fetch_lyrics_from_gemini(title: str, author: str | None = None) -> dict:
    """
    Gọi Gemini API để lấy lời bài hát dựa trên tên bài và tác giả.
    Trả về dict: { "title", "author", "year", "lyrics" } hoặc raise ValueError nếu lỗi.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured")

    song_info = f'"{title}"'
    if author:
        song_info += f' của "{author}"'

    prompt = (
        f"You are a Vietnamese music expert. I need information about the song {song_info}.\n\n"
        "CRITICAL: Return raw text only, NO markdown (no ```json). "
        "NO greetings, NO explanations. Output exactly one JSON object starting with { and ending with }.\n"
        "Required structure:\n"
        "{\n"
        '  "title": "Exact song title with Vietnamese diacritics",\n'
        "  \"author\": \"Composer/Artist (use 'Đang cập nhật' if unknown)\",\n"
        '  "year": "Year composed (leave empty if unknown)",\n'
        '  "lyrics": "Full accurate lyrics. Stanzas separated by exactly two newlines (\\n\\n)."\n'
        "}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1},
        "tools": [{"googleSearch": {}}],
    }

    url = f"{GEMINI_URL}?key={GEMINI_API_KEY}"

    with httpx.Client(timeout=30) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()

    data = response.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError("Gemini returned an empty response")

    ai_text = candidates[0]["content"]["parts"][0]["text"].strip()

    # Extract JSON object — strip any markdown or surrounding text
    json_match = re.search(r"\{[\s\S]*\}", ai_text)
    if not json_match:
        raise ValueError(f"No JSON found in response: {ai_text[:200]}")

    try:
        return json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse error: {e}\nText: {json_match.group(0)[:200]}")
