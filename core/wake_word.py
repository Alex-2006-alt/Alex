"""
ALEX — Wake Word Detection
Listens for "Hey Alex" to activate the assistant.
Uses Whisper-based keyword spotting (no API key required).
"""

import time
import numpy as np
import sounddevice as sd

from utils.logger import log
import config


class WakeWordDetector:
    """
    Always-on wake word detector.
    Listens for the wake phrase (e.g., "Hey Alex") using short Whisper transcriptions.
    Low-resource mode: uses tiny Whisper model for fast keyword detection.
    """

    def __init__(self, wake_word: str | None = None):
        """
        Args:
            wake_word: The phrase to listen for (default from config)
        """
        self.wake_word = (wake_word or config.WAKE_WORD).lower().strip()
        self.wake_variants = self._generate_variants(self.wake_word)
        self.model = None
        self._active = True

        # Short recording settings for wake word detection
        self.chunk_duration = 2.0  # Listen in 2-second chunks
        self.sample_rate = config.SAMPLE_RATE

    def _generate_variants(self, wake_word: str) -> list[str]:
        """
        Generate common misheard/alternative spellings of the wake word.
        Whisper sometimes transcribes "Hey Alex" differently.
        """
        variants = [wake_word]

        # Add common variants
        base_name = wake_word.replace("hey ", "").strip()
        variants.extend([
            f"hey {base_name}",
            f"hay {base_name}",
            f"he {base_name}",
            f"a {base_name}",
            base_name,
            f"okay {base_name}",
            f"hi {base_name}",
            f"hey, {base_name}",
        ])

        return [v.lower().strip() for v in variants]

    def load_model(self):
        """Load a tiny Whisper model for fast wake word detection."""
        if self.model is not None:
            return

        log.info("🔑 Loading wake word detection model (Whisper tiny)...")
        try:
            import whisper
            # Use tiny model for speed — we only need keyword spotting
            self.model = whisper.load_model("tiny")
            log.info("✅ Wake word detector ready")
        except Exception as e:
            log.error(f"Failed to load wake word model: {e}")
            raise

    def listen_for_wake_word(self) -> bool:
        """
        Listen for the wake word in a single audio chunk.

        Returns:
            True if wake word was detected, False otherwise
        """
        self.load_model()

        try:
            # Record a short audio chunk
            num_samples = int(self.chunk_duration * self.sample_rate)
            audio = sd.rec(
                num_samples,
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
            )
            sd.wait()  # Wait for recording to finish

            audio_flat = audio.flatten()

            # Check if there's any meaningful audio (skip silence)
            rms = np.sqrt(np.mean(audio_flat**2))
            if rms < config.SILENCE_THRESHOLD:
                return False

            # Transcribe the short chunk with tiny model
            result = self.model.transcribe(
                audio_flat,
                fp16=False,
                language=config.WHISPER_LANGUAGE or "en",
            )
            text = result["text"].lower().strip()

            if not text:
                return False

            # Check if any wake word variant was said
            for variant in self.wake_variants:
                if variant in text:
                    log.info(f"🔔 Wake word detected! Heard: \"{text}\"")
                    return True

            return False

        except Exception as e:
            log.error(f"Wake word detection error: {e}")
            return False

    def wait_for_wake_word(self) -> None:
        """
        Block until the wake word is detected.
        Continuously listens in short chunks.
        """
        self.load_model()
        log.info(f"👂 Waiting for wake word: \"{self.wake_word}\"")
        print(f"\n   💤 Say \"{self.wake_word.title()}\" to activate...\n")

        self._active = True
        while self._active:
            if self.listen_for_wake_word():
                return
            # Small pause between chunks to prevent CPU overload
            time.sleep(0.1)

    def stop(self):
        """Stop listening for wake word."""
        self._active = False
        log.info("Wake word detector stopped")
