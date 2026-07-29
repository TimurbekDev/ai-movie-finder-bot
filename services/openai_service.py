import base64
import json
import logging

from openai import AsyncOpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Reasoning-family models reject `temperature` and use reasoning_effort instead.
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")

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
- "title" must be the ORIGINAL / international ENGLISH release title (best for database lookup).
- For non-English productions, ALSO put the original-language title (romanized if needed)
  and any well-known release titles into "alternative_titles". Subtitles/dubs in Russian,
  Uzbek, etc. are common — the underlying film is often a Hollywood or international title.
- Distinguish MOVIE vs TV. If TV, you may note a likely season/episode in "reasoning".
- Return 1-4 RANKED candidates, most likely first. Several plausible candidates beat
  one forced wrong answer.
- "year" = 4-digit release year (movie) or first-air year (tv), or null if unsure.
  A wrong year is worse than no year.
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

_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "movie_identification",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["reasoning", "ocr_text", "candidates"],
            "properties": {
                "reasoning": {"type": "string"},
                "ocr_text": {"type": "string"},
                "candidates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "title",
                            "year",
                            "media_type",
                            "confidence",
                            "actors",
                            "alternative_titles",
                        ],
                        "properties": {
                            "title": {"type": "string"},
                            "year": {"type": ["string", "null"]},
                            "media_type": {"type": "string", "enum": ["movie", "tv"]},
                            "confidence": {"type": "integer"},
                            "actors": {"type": "array", "items": {"type": "string"}},
                            "alternative_titles": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
        },
    },
}


def _request_kwargs(content: list[dict], response_format: dict) -> dict:
    kwargs: dict = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "response_format": response_format,
        # Reasoning models spend part of this budget on hidden reasoning tokens.
        "max_completion_tokens": 2500,
    }
    if OPENAI_MODEL.startswith(_REASONING_PREFIXES):
        kwargs["reasoning_effort"] = "low"
    else:
        kwargs["temperature"] = 0.2
    return kwargs


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
        try:
            response = await client.chat.completions.create(**_request_kwargs(content, _RESPONSE_SCHEMA))
        except Exception:
            # Older/custom models may lack strict json_schema support; retry loose.
            logger.warning("Strict schema call failed for %s; retrying with json_object", OPENAI_MODEL)
            response = await client.chat.completions.create(
                **_request_kwargs(content, {"type": "json_object"})
            )
        data = json.loads(response.choices[0].message.content or "")
        if not isinstance(data.get("candidates"), list):
            data["candidates"] = []
        data.setdefault("reasoning", "")
        data.setdefault("ocr_text", "")
        return data
    except Exception:
        logger.exception("OpenAI vision analysis failed")
        return {"reasoning": "", "ocr_text": "", "candidates": []}
