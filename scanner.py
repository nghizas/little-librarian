import base64
import json

import anthropic
from PIL import Image

import config

SCAN_PROMPT = """Look at this photo of a Little Free Library bookshelf. Identify every book visible by reading the spines.

For each book you can see, provide:
- "title": the book title as printed on the spine (best effort)
- "author": the author name if visible (or null if not readable)
- "confidence": "high" if you can clearly read the text, "medium" if partially readable, "low" if you're mostly guessing
- "position": the book's position from left to right (1, 2, 3, ...)
- "spine_color": the dominant color of the spine

Return ONLY a JSON array. No other text. Example:
[
  {"title": "The Great Gatsby", "author": "F. Scott Fitzgerald", "confidence": "high", "position": 1, "spine_color": "blue"},
  {"title": "Unknown - red spine", "author": null, "confidence": "low", "position": 2, "spine_color": "red"}
]

Important:
- Include ALL books visible, even if you can only partially read the spine.
- For books you cannot identify at all, use a descriptive placeholder like "Unknown - [color] spine".
- Do NOT hallucinate titles. If you cannot read it, say so.
- Return valid JSON only."""


def resize_image(image_path):
    """Resize image to fit Claude's max dimension, returns path to resized image."""
    img = Image.open(image_path)
    max_dim = config.MAX_IMAGE_DIMENSION

    if max(img.size) <= max_dim:
        return image_path

    ratio = max_dim / max(img.size)
    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
    img = img.resize(new_size, Image.LANCZOS)

    resized_path = image_path.rsplit(".", 1)[0] + "_resized.jpg"
    img.save(resized_path, "JPEG", quality=85)
    return resized_path


def scan_shelf_photo(image_path):
    """Send a shelf photo to Claude and get back detected books."""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    resized_path = resize_image(image_path)

    with open(resized_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    ext = resized_path.lower().rsplit(".", 1)[-1]
    media_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(ext, "image/jpeg")

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": SCAN_PROMPT},
                ],
            }
        ],
    )

    raw_response = message.content[0].text
    detected = parse_claude_response(raw_response)
    return detected, raw_response


def parse_claude_response(response_text):
    """Parse Claude's JSON response, handling markdown code fences."""
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return json.loads(text)
