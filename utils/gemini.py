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

    raw = json_match.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fallback: extract fields individually when lyrics contain unescaped quotes
    def _extract_field(text: str, key: str) -> str:
        # Match "key": "value" where value runs until the next field or closing brace
        pattern = rf'"{key}"\s*:\s*"([\s\S]*?)"(?=\s*(?:,\s*"|\s*\}}))'
        m = re.search(pattern, text)
        return m.group(1) if m else ""

    title_val = _extract_field(raw, "title")
    author_val = _extract_field(raw, "author")
    year_val = _extract_field(raw, "year")

    # lyrics is the last field — grab everything between "lyrics": " and the final closing "
    lyrics_m = re.search(r'"lyrics"\s*:\s*"([\s\S]*?)"\s*\}?\s*$', raw)
    lyrics_val = lyrics_m.group(1) if lyrics_m else ""

    if not lyrics_val:
        raise ValueError(f"Could not parse Gemini response: {raw[:200]}")

    return {
        "title": title_val,
        "author": author_val,
        "year": year_val,
        "lyrics": lyrics_val.replace("\\n", "\n"),
    }
