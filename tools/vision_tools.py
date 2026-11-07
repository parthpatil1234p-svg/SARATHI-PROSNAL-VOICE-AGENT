"""Desktop screen capture and vision analysis tools."""

import base64
import io
import logging

import mss
from PIL import Image

from config.settings import settings
from tools.registry import register_tool

logger = logging.getLogger("SARATHI.VisionTools")


def grab_desktop_screenshot_base64(max_width: int = 1280) -> str:
    """Captures the primary monitor and encodes it to JPEG Base64."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Primary monitor
        sct_img = sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        # Downsample if larger than max_width to keep inference latency minimal
        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_height = int(float(img.height) * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=80)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return encoded


@register_tool(
    name="analyze_screen",
    description="Captures the user's primary computer monitor screen and answers questions about what is currently visible (e.g., error messages, open IDE code, browser content)."
)
async def analyze_screen(prompt: str = "Describe what is currently visible on the user's screen.") -> str:
    """Takes a screenshot and queries the vision model."""
    try:
        b64_image = grab_desktop_screenshot_base64()

        # If Groq API key is present, use Groq's fast Llama 3.2 Vision model
        if settings.GROQ_API_KEY:
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY)

            response = client.chat.completions.create(
                model=settings.VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"As J.A.R.V.I.S., analyze this screenshot and answer: {prompt}. Speak directly and concisely without markdown asterisks."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                        ]
                    }
                ],
                max_tokens=250,
                temperature=0.2
            )
            return response.choices[0].message.content.strip()

        # Fallback if OpenAI API key is present
        elif settings.OPENAI_API_KEY:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"As J.A.R.V.I.S., concisely describe: {prompt}. No markdown."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                        ]
                    }
                ],
                max_tokens=250
            )
            return response.choices[0].message.content.strip()

        else:
            return "Vision analysis unavailable: Please configure GROQ_API_KEY or OPENAI_API_KEY in .env."

    except Exception as e:
        logger.error(f"Screen analysis error: {e}")
        return f"Unable to analyze screen: {e}"
