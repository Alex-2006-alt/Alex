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

    # ── Record in real-time slices with early breakout on silence ───────
    log.info("🎤 Listening... (speak now)")
    slice_duration = 0.25  # 250ms chunks for low-latency detection
    slice_samples = int(slice_duration * sample_rate)
    silence_slices_needed = max(2, int(silence_duration / slice_duration))
    max_slices = int(max_duration / slice_duration)
    initial_silence_limit = int(6.0 / slice_duration)  # 6 seconds to start speaking

    recorded_slices: list[np.ndarray] = []
    pre_speech_slices: list[np.ndarray] = []
    has_speech = False
    silent_slices = 0

    for slice_idx in range(max_slices):
        try:
            chunk = sd.rec(
                slice_samples,
                samplerate=sample_rate,
                channels=config.CHANNELS,
                dtype="float32",
                device=device,
            )
            sd.wait()
        except Exception as e:
            log.error(f"Recording error: {e}")
            break

        chunk_flat = chunk.flatten()
        rms = float(np.sqrt(np.mean(chunk_flat ** 2)))

        if rms > effective_threshold:
            if not has_speech:
                # Include up to 2 pre-speech chunks (0.5s) to avoid clipping first syllable
                recorded_slices.extend(pre_speech_slices)
            has_speech = True
            silent_slices = 0
            recorded_slices.append(chunk_flat)
        else:
            if has_speech:
                silent_slices += 1
                recorded_slices.append(chunk_flat)
                if silent_slices >= silence_slices_needed:
                    log.info("🔇 Silence detected, stopping recording early")
                    break
            else:
                pre_speech_slices.append(chunk_flat)
                if len(pre_speech_slices) > 2:
                    pre_speech_slices.pop(0)
                # If no speech started within initial silence limit, abort early
                if slice_idx >= initial_silence_limit:
                    log.debug("No speech started within initial timeout")
                    break

    if not has_speech or not recorded_slices:
        log.debug("No speech detected in recording")
        return None

    audio_data = np.concatenate(recorded_slices)
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


def wav_bytes_to_audio(wav_bytes: bytes, target_sample_rate: int = config.SAMPLE_RATE) -> np.ndarray:
    """
    Decode WAV bytes to a float32 numpy array, normalizing to mono and target_sample_rate.
    Works entirely in memory without requiring external ffmpeg binaries.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        frames = wf.readframes(nframes)
        sampwidth = wf.getsampwidth()

        if sampwidth == 2:
            raw = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            raw = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
        elif sampwidth == 1:
            raw = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        else:
            raw = np.frombuffer(frames, dtype=np.float32)

        if channels > 1:
            raw = raw.reshape(-1, channels).mean(axis=1)

        if framerate != target_sample_rate and len(raw) > 0:
            target_len = int(len(raw) * target_sample_rate / framerate)
            raw = np.interp(
                np.linspace(0, len(raw), target_len, endpoint=False),
                np.arange(len(raw)),
                raw,
            ).astype(np.float32)

        return raw.astype(np.float32)


def list_audio_devices():
    """List available audio input devices."""
    devices = sd.query_devices()
    input_devices = []
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            input_devices.append({"index": i, "name": d["name"], "channels": d["max_input_channels"]})
            log.info(f"  🎤 [{i}] {d['name']} ({d['max_input_channels']} channels)")
    return input_devices
