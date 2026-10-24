"""
Unit tests for instant wake word detection and low-latency audio processing.
Verifies:
1. Trailing prompt extraction from wake utterances (e.g. 'Hey Alex what is the weather')
2. Instant query bypassing of the redundant 'Yes?' prompt in Assistant
3. Real-time slice recording and silence breakout in audio_utils
"""

from unittest.mock import patch, MagicMock
import numpy as np
import pytest

from core.wake_word import WakeWordDetector


class TestWakeWordInstant:
    """Test WakeWordDetector variant sorting and prompt extraction."""

    def test_variants_sorted_by_length_descending(self):
        detector = WakeWordDetector(wake_word="hey alex")
        variants = detector.wake_variants
        # Verify longest variants come first so 'hey alex' matches before 'alex'
        assert variants[0] in ("hey alexa", "hey atlas", "okay alex", "hey, alex", "hey alex")
        assert len(variants[0]) >= len(variants[-1])

    def test_trailing_prompt_extracted_when_present(self):
        detector = WakeWordDetector(wake_word="hey alex")
        detector.model = MagicMock()
        detector.model.transcribe.return_value = {"text": "Hey Alex, what is the weather today?"}

        fake_audio = np.ones((32000, 1), dtype=np.float32) * 0.05
        with patch("sounddevice.rec", return_value=fake_audio), patch("sounddevice.wait"):
            detected = detector.listen_for_wake_word()

        assert detected is True
        assert detector.last_prompt == "what is the weather today?"

    def test_trailing_prompt_none_when_only_wake_word_spoken(self):
        detector = WakeWordDetector(wake_word="hey alex")
        detector.model = MagicMock()
        detector.model.transcribe.return_value = {"text": "Hey Alex."}

        fake_audio = np.ones((32000, 1), dtype=np.float32) * 0.05
        with patch("sounddevice.rec", return_value=fake_audio), patch("sounddevice.wait"):
            detected = detector.listen_for_wake_word()

        assert detected is True
        assert detector.last_prompt is None

    def test_wait_for_wake_word_returns_trailing_prompt(self):
        detector = WakeWordDetector(wake_word="hey alex")
        detector.load_model = MagicMock()
        detector.listen_for_wake_word = MagicMock(return_value=True)
        detector.last_prompt = "open youtube"

        prompt = detector.wait_for_wake_word()
        assert prompt == "open youtube"


class TestAssistantInstantWakeFlow:
    """Test that Assistant handles instant queries without redundant prompts."""

    def test_instant_query_skips_yes_and_listen(self):
        from tests.test_listen import _make_assistant

        assistant = _make_assistant(input_mode="voice")
        assistant.use_wake_word = True
        assistant.wake_detector = MagicMock()
        assistant.wake_detector.wait_for_wake_word.return_value = "what time is it"
        assistant.speaker = MagicMock()
        assistant.listen = MagicMock()
        assistant.dispatcher = MagicMock()
        assistant.dispatcher.dispatch.return_value = "The time is 10:00 AM."

        assistant._interaction_loop()

        # Should NOT have spoken 'Yes?' because prompt was already given
        assistant.speaker.say.assert_called_with("The time is 10:00 AM.")
        # Should NOT have called self.listen()
        assistant.listen.assert_not_called()
        # Dispatcher should have received the instant query
        assistant.dispatcher.dispatch.assert_called_once_with("what time is it")

    def test_bare_wake_word_speaks_yes_and_listens(self):
        from tests.test_listen import _make_assistant

        assistant = _make_assistant(input_mode="voice")
        assistant.use_wake_word = True
        assistant.wake_detector = MagicMock()
        assistant.wake_detector.wait_for_wake_word.return_value = None
        assistant.speaker = MagicMock()
        assistant.listen = MagicMock(return_value="what time is it")
        assistant.dispatcher = MagicMock()
        assistant.dispatcher.dispatch.return_value = "The time is 10:00 AM."

        assistant._interaction_loop()

        # Should have spoken 'Yes?' first
        assistant.speaker.say.assert_any_call("Yes?", block=True)
        # Should have called self.listen()
        assistant.listen.assert_called_once()
        # Dispatcher should have received user input
        assistant.dispatcher.dispatch.assert_called_once_with("what time is it")


class TestAudioRecordingEarlyBreakout:
    """Test that audio_utils.record_audio_until_silence breaks early on silence."""

    def test_recording_breaks_early_on_speech_then_silence(self):
        from utils.audio_utils import record_audio_until_silence

        # Simulate 1 slice of pre-speech, 2 slices of speech (RMS 0.05), then 6 slices of silence (RMS 0.0001)
        slice_samples = int(0.25 * 16000)
        silent_chunk = np.zeros((slice_samples, 1), dtype=np.float32)
        speech_chunk = np.ones((slice_samples, 1), dtype=np.float32) * 0.05

        chunks = [
            silent_chunk,      # pre-speech
            speech_chunk,      # speech 1
            speech_chunk,      # speech 2
            silent_chunk,      # silence 1
            silent_chunk,      # silence 2
            silent_chunk,      # silence 3
            silent_chunk,      # silence 4
            silent_chunk,      # silence 5
            silent_chunk,      # silence 6 -> stops here
            speech_chunk,      # should never be reached!
        ]

        chunk_iter = iter(chunks)

        def fake_rec(samples, **kwargs):
            return next(chunk_iter, silent_chunk)

        with patch("sounddevice.rec", side_effect=fake_rec), patch("sounddevice.wait"):
            audio = record_audio_until_silence(
                sample_rate=16000,
                silence_threshold=0.001,
                silence_duration=1.0,
                max_duration=30.0,
            )

        assert audio is not None
        # Verify it broke early and did not record all 30 seconds (120 slices)
        assert len(audio) < int(10 * 16000)
