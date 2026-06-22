import base64
import json
import logging
from collections import Counter

from openai import AsyncOpenAI

from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

PROMPT = """Analyze this movie or TV show screenshot.

Identify:
- Movie or TV show name
- Release year
- Main actors visible or known for the scene
- Brief scene description

Respond ONLY with valid JSON in this exact format:
{"title": "...", "year": "...", "actors": ["...", "..."], "scene": "...", "confidence": "NN%"}

If you cannot identify the movie or show, set "title" to null.
"""


async def analyze_image(image_bytes: bytes) -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        logger.exception("OpenAI vision analysis failed")
        return {"title": None, "confidence": "0%"}


def aggregate_frame_results(results: list[dict]) -> dict:
    titles = [r["title"] for r in results if r.get("title")]
    if not titles:
        return {"title": None, "confidence": "0%"}

    most_common_title, _ = Counter(titles).most_common(1)[0]
    matching = [r for r in results if r.get("title") == most_common_title]

    confidences = []
    for r in matching:
        try:
            confidences.append(float(str(r.get("confidence", "0")).replace("%", "")))
        except ValueError:
            pass
    avg_conf = sum(confidences) / len(confidences) if confidences else 0

    return {
        "title": most_common_title,
        "year": matching[0].get("year"),
        "confidence": f"{avg_conf:.0f}%",
    }
