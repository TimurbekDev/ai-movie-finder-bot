import base64
import json
import logging

from openai import AsyncOpenAI

from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are an expert film & TV identifier (cinephile + archivist).
You receive one or more frames from the SAME movie or TV episode, plus any OCR text.

Reason step by step internally, then output JSON ONLY.

Use every available signal:
- Actors / recognizable faces (name them if you know them)
- On-screen text: subtitles, title cards, channel logos/watermarks (Netflix/HBO/...),
  lower-third name tags
- Setting, era, costumes, props, cars, technology, color grade, film stock, aspect ratio
- Genre and cinematography style

Rules:
- Prefer the ORIGINAL / international English title (best for database lookup).
- Distinguish MOVIE vs TV. If TV, you may note a likely season/episode in "reasoning".
- Return 1-4 RANKED candidates, most likely first. Several plausible candidates beat
  one forced wrong answer.
- "year" = 4-digit release year (movie) or first-air year (tv), or null.
- "confidence" = your CALIBRATED probability THIS candidate is correct (0-100). Be honest:
  blurry / generic shot / unknown actors => low. Do not inflate.
- "actors" = real-world actor names you recognize in the frames for that title (may be []).
- Never invent a title just to seem confident. If truly unidentifiable, return "candidates": [].

Output EXACTLY this JSON shape:
{
  "reasoning": "<short: which signals drove the guess>",
  "ocr_text": "<readable on-screen text you used, or ''>",
  "candidates": [
    {"title": "", "year": "", "media_type": "movie|tv", "confidence": 0,
     "actors": [], "alternative_titles": []}
  ]
}"""

_USER_TEXT = "Identify this title. {n} frame(s) from the same scene/clip. OCR (may be empty/noisy): {ocr}"


async def analyze(images: list[bytes], ocr_text: str = "") -> dict:
    """Single multi-image vision call -> reasoning + OCR + ranked candidates."""
    if not images:
        return {"reasoning": "", "ocr_text": "", "candidates": []}

    content = [{"type": "text", "text": _USER_TEXT.format(n=len(images), ocr=ocr_text[:1500])}]
    for img in images:
        b64 = base64.b64encode(img).decode()
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
            }
        )

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=700,
        )
        data = json.loads(response.choices[0].message.content)
        if not isinstance(data.get("candidates"), list):
            data["candidates"] = []
        data.setdefault("reasoning", "")
        data.setdefault("ocr_text", "")
        return data
    except Exception:
        logger.exception("OpenAI vision analysis failed")
        return {"reasoning": "", "ocr_text": "", "candidates": []}
