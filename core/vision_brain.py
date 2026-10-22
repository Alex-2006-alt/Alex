"""
ALEX — Vision Brain
Answers questions about images (screenshots) using multimodal LLMs.

Provider priority
-----------------
1. Gemini 1.5 Flash / gemini-1.5-flash-latest  (free tier, built-in vision)
2. OpenRouter vision model (llava-llama-3 or similar free model)
3. OpenAI GPT-4o-mini                           (if OPENAI_API_KEY is set)

The image is passed as base64-encoded PNG.  A short system prompt tells the
model it is looking at the user's screen and should answer concisely in
natural conversational English suitable for text-to-speech.
"""

import base64
from utils.logger import log
import config


_SYSTEM_PROMPT = (
    "You are ALEX, a helpful AI assistant. The user has shared a screenshot "
    "of their screen with you. Look at the image carefully and answer the "
    "user's question directly, concisely, and in plain conversational English "
    "— your answer will be read aloud by a text-to-speech engine, so never "
    "use markdown, bullet points, or special formatting. "
    "Keep the answer under 4 sentences unless the user explicitly asks for more detail."
)


class VisionBrain:
    """
    Multimodal LLM wrapper — takes a base64 image and a question, returns
    a plain-text answer suitable for TTS.
    """

    def __init__(self):
        self._provider = config.VISION_PROVIDER

    # ─── Public API ───────────────────────────────────────────────────────────

    def ask_about_image(self, image_b64: str, question: str) -> str:
        """
        Ask a question about a base64-encoded PNG image.
        Returns a plain-text answer string.
        """
        log.info(f"👁️  VisionBrain: analyzing screenshot ({self._provider})")

        providers = self._get_provider_order()
        last_error = "No vision provider available"

        for provider in providers:
            try:
                if provider == "gemini":
                    return self._ask_gemini(image_b64, question)
                elif provider == "openrouter":
                    return self._ask_openrouter(image_b64, question)
                elif provider == "openai":
                    return self._ask_openai(image_b64, question)
            except Exception as e:
                log.warning(f"VisionBrain ({provider}) failed: {e}")
                last_error = str(e)
                continue

        return f"Sorry, I couldn't analyze the screen right now. {last_error}"

    # ─── Provider implementations ─────────────────────────────────────────────

    def _ask_gemini(self, image_b64: str, question: str) -> str:
        """Use Gemini multimodal API (google-generativeai)."""
        import google.generativeai as genai

        if not config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not set")

        genai.configure(api_key=config.GEMINI_API_KEY)

        # Use the vision-capable model — gemini-1.5-flash supports images well
        # and has a generous free tier.  Fall back to the configured model if
        # it also supports vision (gemini-2.0-flash, gemini-3.x-flash, etc.)
        vision_model_name = config.VISION_GEMINI_MODEL

        model = genai.GenerativeModel(
            model_name=vision_model_name,
            system_instruction=_SYSTEM_PROMPT,
        )

        image_part = {
            "inline_data": {
                "mime_type": "image/png",
                "data": image_b64,
            }
        }

        response = model.generate_content([image_part, question])
        text = response.text.strip()
        log.info(f"👁️  Gemini vision answer ({len(text)} chars)")
        return text

    def _ask_openrouter(self, image_b64: str, question: str) -> str:
        """Use an OpenRouter vision model (OpenAI-compatible API)."""
        from openai import OpenAI

        if not config.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY not set")

        client = OpenAI(
            api_key=config.OPENROUTER_API_KEY,
            base_url=config.OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://github.com/alex-assistant",
                "X-Title": "ALEX Personal Assistant",
            },
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        },
                    },
                    {"type": "text", "text": question},
                ],
            },
        ]

        resp = client.chat.completions.create(
            model=config.VISION_OPENROUTER_MODEL,
            messages=messages,
            max_tokens=512,
        )
        text = resp.choices[0].message.content.strip()
        log.info(f"👁️  OpenRouter vision answer ({len(text)} chars)")
        return text

    def _ask_openai(self, image_b64: str, question: str) -> str:
        """Use OpenAI GPT-4o-mini with vision support."""
        from openai import OpenAI

        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set")

        client = OpenAI(api_key=config.OPENAI_API_KEY)

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        },
                    },
                    {"type": "text", "text": question},
                ],
            },
        ]

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=512,
        )
        text = resp.choices[0].message.content.strip()
        log.info(f"👁️  OpenAI vision answer ({len(text)} chars)")
        return text

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _get_provider_order(self) -> list[str]:
        """Return providers to try, in priority order."""
        primary = self._provider
        all_providers = ["gemini", "openrouter", "openai"]
        # Put the configured primary first, then the rest as fallbacks
        ordered = [primary] + [p for p in all_providers if p != primary]
        return ordered
