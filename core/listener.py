"""
ALEX — Speech-to-Text Listener
Uses OpenAI Whisper to transcribe spoken audio into text.
"""

import tempfile
from pathlib import Path

import numpy as np

from utils.logger import log
from utils.audio_utils import record_audio_until_silence, save_audio_to_wav
import config


class Listener:
    """
    Listens to microphone input and transcribes speech to text using Whisper.
    """

    def __init__(self, model_size: str | None = None, language: str | None = None):
        """
        Initialize the Whisper listener.

        Args:
            model_size: Whisper model size (tiny/base/small/medium/large)
            language: Language code (e.g., 'en') or None for auto-detect
        """
        self.model_size = model_size or config.WHISPER_MODEL_SIZE
        self.language = language or config.WHISPER_LANGUAGE
        self.model = None

    def load_model(self):
        """Load the Whisper model (lazy loading — only when first needed)."""
        if self.model is not None:
            return

        log.info(f"🧠 Loading Whisper model '{self.model_size}'... (this may take a moment)")
        try:
            import whisper
            self.model = whisper.load_model(self.model_size)
            log.info(f"✅ Whisper model '{self.model_size}' loaded successfully")
        except Exception as e:
            log.error(f"Failed to load Whisper model: {e}")
            raise

    def listen(self) -> str | None:
        """
        Record audio from the microphone and transcribe it.

        Returns:
            Transcribed text string, or None if nothing was heard
        """
        self.load_model()

        # Record audio until silence
        audio_data = record_audio_until_silence()
        if audio_data is None:
            return None

        # Transcribe with Whisper
        return self.transcribe(audio_data)

    def transcribe(self, audio_data: np.ndarray) -> str | None:
        """
        Transcribe audio data to text.

        Args:
            audio_data: numpy array of audio samples (float32, 16kHz)

        Returns:
            Transcribed text, or None on failure
        """
        self.load_model()

        try:
            log.info("🔄 Transcribing audio...")

            # Whisper expects float32 numpy array
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # Run transcription
            options = {
                "fp16": False,  # Use fp32 for CPU compatibility
            }
            if self.language:
                options["language"] = self.language

            result = self.model.transcribe(audio_data, **options)
            text = result["text"].strip()

            if text:
                log.info(f"🗣️ You said: \"{text}\"")
                return text
            else:
                log.debug("Whisper returned empty transcription")
                return None

        except Exception as e:
            log.error(f"Transcription error: {e}")
            return None

    def transcribe_file(self, audio_path: str | Path) -> str | None:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to the audio file (WAV, MP3, etc.)

        Returns:
            Transcribed text, or None on failure
        """
        self.load_model()

        try:
            log.info(f"🔄 Transcribing file: {audio_path}")
            options = {"fp16": False}
            if self.language:
                options["language"] = self.language

            result = self.model.transcribe(str(audio_path), **options)
            text = result["text"].strip()

            if text:
                log.info(f"📝 Transcription: \"{text}\"")
                return text
            return None

        except Exception as e:
            log.error(f"File transcription error: {e}")
            return None
