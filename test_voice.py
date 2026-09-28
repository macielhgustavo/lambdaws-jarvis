import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_arch.voice import (
    FRAME_BYTES,
    VoiceConfig,
    VoiceRuntime,
    OpenWakeWordDetector,
    rms,
    write_wav,
)


class FakeSource:
    def __init__(self, frames):
        self._frames = list(frames)
        self.closed = False
    def start(self): pass
    def frames(self):
        while self._frames:
            yield self._frames.pop(0)
    def close(self):
        self.closed = True


class FakeDetector:
    available = True
    def __init__(self):
        self.calls = 0
    def detected(self, frame):
        self.calls += 1
        return self.calls == 1


class FakeSTT:
    def transcribe(self, path):
        return "como está o pc", "fake-stt"


class FakeSpeaker:
    def __init__(self):
        self.spoken = []
        self.stopped = False
    def speak(self, text):
        self.spoken.append(text)
        return True
    def stop(self):
        self.stopped = True


class FakeAgent:
    def ask(self, prompt):
        return f"resposta:{prompt}", "fake-model"


class VoiceTests(unittest.TestCase):
    def test_rms_zero(self):
        self.assertEqual(rms(b"\x00" * FRAME_BYTES), 0.0)

    def test_write_wav(self):
        path = write_wav([b"\x00" * FRAME_BYTES])
        try:
            self.assertGreater(path.stat().st_size, 44)
        finally:
            path.unlink(missing_ok=True)

    def test_runtime_handles_wake_command_and_tts(self):
        loud = (1000).to_bytes(2, "little", signed=True) * (FRAME_BYTES // 2)
        silent = b"\x00" * FRAME_BYTES
        source = FakeSource([loud, loud] + [silent] * 20)
        speaker = FakeSpeaker()
        runtime = VoiceRuntime(
            FakeAgent(),
            config=VoiceConfig(
                silence_seconds=0.0,
                min_command_seconds=0.0,
                max_command_seconds=1.0,
                vad_rms_threshold=100,
            ),
            source=source,
            detector=FakeDetector(),
            stt=FakeSTT(),
            speaker=speaker,
        )
        states = []
        runtime.on_state = states.append
        runtime.run_forever()
        self.assertIn("awake", states)
        self.assertEqual(speaker.spoken, ["resposta:como está o pc"])
        self.assertTrue(source.closed)

    def test_detector_matches_jarvis_label(self):
        detector = OpenWakeWordDetector("hey jarvis", threshold=0.5)
        class Model:
            def predict(self, frame):
                return {"hey_jarvis": 0.8, "alexa": 0.1}
        detector._model = Model()
        self.assertTrue(detector.detected(b"x"))

    def test_default_config_targets_jarvis(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(VoiceConfig.from_env().wake_model, "hey jarvis")


if __name__ == "__main__":
    unittest.main()
