"""
ALEX — Audio Utilities
Helpers for recording, processing, and saving audio.
"""

import io
import wave
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd

from utils.logger import log
import config


def record_audio_until_silence(
    sample_rate: int = config.SAMPLE_RATE,
    silence_threshold: float = config.SILENCE_THRESHOLD,
    silence_duration: float = config.SILENCE_DURATION,
    max_duration: float = config.RECORD_SECONDS_MAX,
    block_size: int = config.AUDIO_BLOCK_SIZE,
) -> np.ndarray | None:
    """
    Record audio from the microphone until silence is detected.

    Uses ``sd.rec()`` for maximum device compatibility (including WDM-KS
    devices that don't support ``sd.InputStream`` blocking mode).
    Automatically calibrates the silence threshold against ambient noise.

    Args:
        sample_rate: Audio sample rate in Hz
        silence_threshold: RMS amplitude below which is considered silence
        silence_duration: Seconds of silence needed to stop recording
        max_duration: Maximum recording duration in seconds
        block_size: Audio buffer block size (used for chunk analysis)

    Returns:
        numpy array of audio data, or None if nothing meaningful was recorded
    """
    device = config.AUDIO_INPUT_DEVICE

    # ── Ambient noise calibration ──────────────────────────────────────
    try:
        calibration_samples = int(0.5 * sample_rate)  # 0.5 seconds
        ambient = sd.rec(
            calibration_samples,
            samplerate=sample_rate,
            channels=config.CHANNELS,
            dtype="float32",
            device=device,
        )
        sd.wait()
        ambient_rms = float(np.sqrt(np.mean(ambient ** 2)))
        effective_threshold = max(silence_threshold, ambient_rms * 3.0)
        log.info(
            f"🔇 Ambient RMS: {ambient_rms:.6f} | "
            f"Configured threshold: {silence_threshold} | "
            f"Effective threshold: {effective_threshold:.6f}"
        )
    except Exception as e:
        log.warning(f"Ambient calibration failed, using configured threshold: {e}")
        effective_threshold = silence_threshold

    # ── Record full max_duration in one shot ───────────────────────────
    log.info("🎤 Listening... (speak now)")
    total_samples = int(max_duration * sample_rate)

    try:
        audio = sd.rec(
            total_samples,
            samplerate=sample_rate,
            channels=config.CHANNELS,
            dtype="float32",
            device=device,
        )
        sd.wait()
    except Exception as e:
        log.error(f"Recording error: {e}")
        return None

    audio = audio.flatten()

    # ── Analyze chunks to find speech boundaries ──────────────────────
    silence_chunks_needed = int(silence_duration * sample_rate / block_size)
    total_chunks = len(audio) // block_size

    has_speech = False
    speech_start = 0
    speech_end = len(audio)
    silent_chunks = 0

    for i in range(total_chunks):
        chunk = audio[i * block_size : (i + 1) * block_size]
        rms = float(np.sqrt(np.mean(chunk ** 2)))

        if rms > effective_threshold:
            if not has_speech:
                # Mark where speech starts (back up one chunk for safety)
                speech_start = max(0, (i - 1) * block_size)
            has_speech = True
            silent_chunks = 0
            speech_end = (i + 1) * block_size
        else:
            silent_chunks += 1

        # Stop scanning after enough silence post-speech
        if has_speech and silent_chunks >= silence_chunks_needed:
            log.info("🔇 Silence detected, stopping")
            break

    if not has_speech:
        log.debug("No speech detected in recording")
        return None

    # Trim to just the speech portion (with a small tail)
    audio_data = audio[speech_start:speech_end]
    duration = len(audio_data) / sample_rate
    log.info(f"📼 Recorded {duration:.1f}s of audio")

    return audio_data




def save_audio_to_wav(
    audio_data: np.ndarray,
    filepath: Path | str | None = None,
    sample_rate: int = config.SAMPLE_RATE,
) -> Path:
    """
    Save audio data as a WAV file.

    Args:
        audio_data: numpy array of audio samples
        filepath: Output file path (auto-generated if None)
        sample_rate: Audio sample rate

    Returns:
        Path to the saved WAV file
    """
    if filepath is None:
        filepath = Path(tempfile.mktemp(suffix=".wav"))
    else:
        filepath = Path(filepath)

    # Convert float32 to int16 for WAV
    audio_int16 = (audio_data * 32767).astype(np.int16)

    with wave.open(str(filepath), "w") as wf:
        wf.setnchannels(config.CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())

    return filepath


def audio_to_bytes(audio_data: np.ndarray, sample_rate: int = config.SAMPLE_RATE) -> bytes:
    """Convert numpy audio array to WAV bytes (for in-memory processing)."""
    buffer = io.BytesIO()
    audio_int16 = (audio_data * 32767).astype(np.int16)

    with wave.open(buffer, "w") as wf:
        wf.setnchannels(config.CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())

    return buffer.getvalue()


def list_audio_devices():
    """List available audio input devices."""
    devices = sd.query_devices()
    input_devices = []
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            input_devices.append({"index": i, "name": d["name"], "channels": d["max_input_channels"]})
            log.info(f"  🎤 [{i}] {d['name']} ({d['max_input_channels']} channels)")
    return input_devices
