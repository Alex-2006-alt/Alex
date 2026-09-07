"""
ALEX — Text-to-Speech Speaker
Converts text responses into spoken audio output.
"""

import threading

from utils.logger import log
import config


class Speaker:
    """
    Text-to-Speech engine that speaks responses aloud.
    Supports pyttsx3 (offline, basic) with a clean non-blocking interface.
    """

    def __init__(self, engine_type: str | None = None):
        """
        Initialize the TTS engine.

        Args:
            engine_type: 'pyttsx3' or 'coqui'
        """
        self.engine_type = engine_type or config.TTS_ENGINE
        self.engine = None
        self._speaking = False
        self._lock = threading.Lock()

    def _init_engine(self):
        """Initialize the TTS engine (lazy loading)."""
        if self.engine is not None:
            return

        if self.engine_type == "pyttsx3":
            self._init_pyttsx3()
        else:
            log.warning(f"Unknown TTS engine '{self.engine_type}', falling back to pyttsx3")
            self.engine_type = "pyttsx3"
            self._init_pyttsx3()

    def _init_pyttsx3(self):
        """Initialize pyttsx3 engine."""
        try:
            import pyttsx3

            self.engine = pyttsx3.init()

            # Configure voice properties
            self.engine.setProperty("rate", config.TTS_RATE)
            self.engine.setProperty("volume", config.TTS_VOLUME)

            # Try to set a natural-sounding voice
            voices = self.engine.getProperty("voices")
            if voices:
                # Prefer a female voice for variety, but use whatever is available
                # Voice index 0 is usually male, index 1 is usually female on Windows
                preferred_index = 1 if len(voices) > 1 else 0
                self.engine.setProperty("voice", voices[preferred_index].id)

                log.info(f"🔊 TTS initialized with voice: {voices[preferred_index].name}")
            else:
                log.info("🔊 TTS initialized with default voice")

        except Exception as e:
            log.error(f"Failed to initialize pyttsx3: {e}")
            raise

    def say(self, text: str, block: bool = True):
        """
        Speak the given text aloud.

        Args:
            text: Text to speak
            block: If True, wait for speech to finish. If False, speak in background.
        """
        if not text or not text.strip():
            return

        self._init_engine()

        # Clean the text for speech
        clean_text = self._clean_for_speech(text)
        log.info(f"🔊 Speaking: \"{clean_text[:80]}{'...' if len(clean_text) > 80 else ''}\"")

        if block:
            self._speak_blocking(clean_text)
        else:
            self._speak_async(clean_text)

    def _speak_blocking(self, text: str):
        """Speak text and wait for completion."""
        with self._lock:
            self._speaking = True
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception as e:
                log.error(f"Speech error: {e}")
            finally:
                self._speaking = False

    def _speak_async(self, text: str):
        """Speak text in a background thread."""
        thread = threading.Thread(target=self._speak_blocking, args=(text,), daemon=True)
        thread.start()

    def stop(self):
        """Stop any ongoing speech."""
        if self.engine and self._speaking:
            try:
                self.engine.stop()
                self._speaking = False
                log.info("🔇 Speech stopped")
            except Exception as e:
                log.error(f"Error stopping speech: {e}")

    @property
    def is_speaking(self) -> bool:
        """Check if the engine is currently speaking."""
        return self._speaking

    def set_rate(self, rate: int):
        """Set speech rate (words per minute). Default is 175."""
        self._init_engine()
        self.engine.setProperty("rate", rate)
        log.info(f"Speech rate set to {rate} WPM")

    def set_volume(self, volume: float):
        """Set speech volume (0.0 to 1.0)."""
        self._init_engine()
        volume = max(0.0, min(1.0, volume))
        self.engine.setProperty("volume", volume)
        log.info(f"Speech volume set to {volume}")

    def list_voices(self) -> list[dict]:
        """List all available TTS voices."""
        self._init_engine()
        voices = self.engine.getProperty("voices")
        voice_list = []
        for v in voices:
            voice_list.append({
                "id": v.id,
                "name": v.name,
                "languages": v.languages,
            })
            log.info(f"  🗣️ {v.name}")
        return voice_list

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """
        Clean text for better speech output.
        Removes code blocks, URLs, special characters, etc.
        """
        import re

        # Remove action code blocks (```action ... ```)
        text = re.sub(r"```action\s*\n.*?```", "", text, flags=re.DOTALL)
        # Remove any remaining code blocks
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        # Remove markdown formatting
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # Bold
        text = re.sub(r"\*(.+?)\*", r"\1", text)  # Italic
        text = re.sub(r"`(.+?)`", r"\1", text)  # Inline code
        # Remove URLs
        text = re.sub(r"https?://\S+", "a link", text)
        # Remove excess whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text
