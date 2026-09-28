"""Always-on voice runtime for LambdaWS Jarvis.

The base module intentionally depends only on the standard library. Optional
backends (openWakeWord / faster-whisper / Piper) are loaded dynamically so the
main Jarvis installation keeps working even when a voice extra is unavailable.
"""

from __future__ import annotations

import array
import importlib
import importlib.util
import math
import os
import shutil
import signal
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
FRAME_MS = 80
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * SAMPLE_WIDTH


@dataclass(slots=True)
class VoiceConfig:
    wake_model: str | None = "hey jarvis"
    wake_threshold: float = 0.55
    silence_seconds: float = 1.15
    max_command_seconds: float = 18.0
    min_command_seconds: float = 0.45
    vad_rms_threshold: int = 420
    stt_model: str = "small"
    language: str = "pt"
    piper_model: str | None = None

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        def number(name: str, default: float) -> float:
            try:
                return float(os.environ.get(name, default))
            except ValueError:
                return default

        return cls(
            wake_model=os.environ.get("JARVIS_WAKEWORD_MODEL", "hey jarvis") or "hey jarvis",
            wake_threshold=number("JARVIS_WAKE_THRESHOLD", 0.55),
            silence_seconds=number("JARVIS_VOICE_SILENCE", 1.15),
            max_command_seconds=number("JARVIS_VOICE_MAX_COMMAND", 18.0),
            min_command_seconds=number("JARVIS_VOICE_MIN_COMMAND", 0.45),
            vad_rms_threshold=int(number("JARVIS_VOICE_RMS", 420)),
            stt_model=os.environ.get("JARVIS_STT_MODEL", "small"),
            language=os.environ.get("JARVIS_VOICE_LANGUAGE", "pt"),
            piper_model=os.environ.get("JARVIS_PIPER_MODEL") or None,
        )


class VoiceBackendUnavailable(RuntimeError):
    pass


class PipeWireInput:
    """Continuous 16 kHz mono s16 stream from PipeWire stdout."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None

    @property
    def available(self) -> bool:
        return shutil.which("pw-record") is not None

    def start(self) -> None:
        if self.process is not None:
            return
        if not self.available:
            raise VoiceBackendUnavailable("pw-record não encontrado.")
        self.process = subprocess.Popen(
            [
                "pw-record",
                "--raw",
                "--rate",
                str(SAMPLE_RATE),
                "--channels",
                str(CHANNELS),
                "--format",
                "s16",
                "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

    def frames(self) -> Iterable[bytes]:
        self.start()
        assert self.process is not None and self.process.stdout is not None
        while self.process.poll() is None:
            chunk = self.process.stdout.read(FRAME_BYTES)
            if not chunk:
                break
            if len(chunk) < FRAME_BYTES:
                chunk += b"\x00" * (FRAME_BYTES - len(chunk))
            yield chunk

    def close(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
            try:
                self.process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
        self.process = None


def rms(frame: bytes) -> float:
    if not frame:
        return 0.0
    samples = array.array("h")
    samples.frombytes(frame)
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


class OpenWakeWordDetector:
    """openWakeWord adapter loaded only when the optional package exists."""

    def __init__(self, model_path: str, threshold: float = 0.55) -> None:
        self.model_path = model_path
        self.threshold = threshold
        self._model = None

    @property
    def available(self) -> bool:
        try:
            return importlib.util.find_spec("openwakeword.model") is not None
        except (ImportError, AttributeError):
            return False

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            module = importlib.import_module("openwakeword.model")
        except ImportError as error:
            raise VoiceBackendUnavailable(
                "openWakeWord não instalado no ambiente de voz."
            ) from error

        configured = str(self.model_path or "hey jarvis").strip()
        path = Path(configured).expanduser()
        if path.is_file():
            self._model = module.Model(
                wakeword_models=[str(path)],
                inference_framework="onnx",
            )
        else:
            self._model = module.Model(
                wakeword_models=[configured.replace("_", " ")],
                inference_framework="onnx",
            )
        return self._model

    def detected(self, frame: bytes) -> bool:
        model = self._load()
        predictions = model.predict(frame)
        if not predictions:
            return False

        target = str(self.model_path or "hey jarvis").lower().replace("_", " ")
        matching = [
            float(value)
            for name, value in predictions.items()
            if target in str(name).lower().replace("_", " ")
            or ("jarvis" in target and "jarvis" in str(name).lower())
        ]
        scores = matching or [float(value) for value in predictions.values()]
        return max(scores) >= self.threshold


class FasterWhisperSTT:
    def __init__(self, model_name: str = "small", language: str = "pt") -> None:
        self.model_name = model_name
        self.language = language
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            module = importlib.import_module("faster_whisper")
        except ImportError as error:
            raise VoiceBackendUnavailable("faster-whisper não instalado.") from error

        device = os.environ.get("JARVIS_STT_DEVICE", "cpu")
        compute = os.environ.get(
            "JARVIS_STT_COMPUTE",
            "int8" if device == "cpu" else "int8_float16",
        )
        self._model = module.WhisperModel(
            self.model_name,
            device=device,
            compute_type=compute,
        )
        return self._model

    def transcribe(self, wav_path: Path) -> str:
        model = self._load()
        segments, _ = model.transcribe(
            str(wav_path),
            language=self.language,
            vad_filter=True,
            beam_size=1,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()


class GroqSTT:
    def __init__(self, language: str = "pt") -> None:
        self.language = language

    def transcribe(self, wav_path: Path) -> str:
        if not os.environ.get("GROQ_API_KEY"):
            raise VoiceBackendUnavailable("GROQ_API_KEY não configurada.")
        try:
            from groq import Groq
        except ImportError as error:
            raise VoiceBackendUnavailable("Pacote groq indisponível.") from error

        with Groq(timeout=45, max_retries=0) as client, wav_path.open("rb") as audio:
            result = client.audio.transcriptions.create(
                file=audio,
                model="whisper-large-v3-turbo",
                language=self.language,
                response_format="text",
            )
        return (result if isinstance(result, str) else str(result)).strip()


class HybridSTT:
    def __init__(self, config: VoiceConfig) -> None:
        self.local = FasterWhisperSTT(config.stt_model, config.language)
        self.cloud = GroqSTT(config.language)

    def transcribe(self, wav_path: Path) -> tuple[str, str]:
        try:
            text = self.local.transcribe(wav_path)
            if text:
                return text, "faster-whisper"
        except Exception:
            pass

        text = self.cloud.transcribe(wav_path)
        return text, "groq-whisper"


class PiperSpeaker:
    """Local TTS with Piper. Speech can be interrupted with stop()."""

    def __init__(self, model_path: str | None) -> None:
        self.model_path = model_path
        self.process: subprocess.Popen | None = None

    @property
    def available(self) -> bool:
        return bool(
            self.model_path
            and Path(self.model_path).is_file()
            and shutil.which("piper")
            and shutil.which("pw-play")
        )

    def speak(self, text: str) -> bool:
        if not self.available or not text.strip():
            return False

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)

        try:
            synth = subprocess.run(
                [
                    "piper",
                    "--model",
                    self.model_path,
                    "--output_file",
                    str(wav_path),
                ],
                input=text,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
                check=False,
            )
            if synth.returncode != 0 or wav_path.stat().st_size <= 44:
                return False
            self.process = subprocess.Popen(
                ["pw-play", str(wav_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.process.wait()
            return True
        finally:
            self.process = None
            wav_path.unlink(missing_ok=True)

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()


def write_wav(frames: list[bytes]) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = Path(tmp.name)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"".join(frames))
    return path


class VoiceRuntime:
    """Wake word -> command capture -> STT -> Jarvis -> TTS loop.

    Saying the wake word while TTS is active interrupts playback and starts a
    fresh command (barge-in).
    """

    def __init__(
        self,
        agent,
        *,
        config: VoiceConfig | None = None,
        source: PipeWireInput | None = None,
        detector: OpenWakeWordDetector | None = None,
        stt: HybridSTT | None = None,
        speaker: PiperSpeaker | None = None,
        on_state: Callable[[str], None] | None = None,
        on_transcript: Callable[[str], None] | None = None,
        on_response: Callable[[str], None] | None = None,
    ) -> None:
        self.agent = agent
        self.config = config or VoiceConfig.from_env()
        self.source = source or PipeWireInput()
        self.detector = detector or OpenWakeWordDetector(
            self.config.wake_model or "",
            self.config.wake_threshold,
        )
        self.stt = stt or HybridSTT(self.config)
        self.speaker = speaker or PiperSpeaker(self.config.piper_model)
        self.on_state = on_state or (lambda _: None)
        self.on_transcript = on_transcript or (lambda _: None)
        self.on_response = on_response or (lambda _: None)
        self.running = False

    def _capture_command(self, first_frame: bytes | None = None) -> list[bytes]:
        frames = [first_frame] if first_frame else []
        started = time.monotonic()
        last_voice = started
        heard_voice = False

        for frame in self.source.frames():
            frames.append(frame)
            now = time.monotonic()
            if rms(frame) >= self.config.vad_rms_threshold:
                heard_voice = True
                last_voice = now

            elapsed = now - started
            if elapsed >= self.config.max_command_seconds:
                break
            if (
                heard_voice
                and elapsed >= self.config.min_command_seconds
                and now - last_voice >= self.config.silence_seconds
            ):
                break

        return frames

    def _handle_command(self, frames: list[bytes]) -> None:
        if not frames:
            return
        wav_path = write_wav(frames)
        try:
            self.on_state("transcribing")
            transcript, backend = self.stt.transcribe(wav_path)
        finally:
            wav_path.unlink(missing_ok=True)

        transcript = transcript.strip()
        if not transcript:
            self.on_state("listening")
            return

        self.on_transcript(transcript)
        self.on_state("thinking")
        response, model_backend = self.agent.ask(transcript)
        self.on_response(response)
        self.on_state(f"speaking:{model_backend}:{backend}")
        self.speaker.speak(response)
        self.on_state("listening")

    def run_forever(self) -> None:
        if not self.detector.available:
            raise VoiceBackendUnavailable(
                "Wake word indisponível: instale openWakeWord no ambiente de voz."
            )

        self.running = True
        self.source.start()
        self.on_state("listening")

        try:
            for frame in self.source.frames():
                if not self.running:
                    break
                if self.detector.detected(frame):
                    self.speaker.stop()
                    self.on_state("awake")
                    frames = self._capture_command()
                    self._handle_command(frames)
        finally:
            self.source.close()
            self.speaker.stop()
            self.running = False

    def stop(self) -> None:
        self.running = False
        self.speaker.stop()
        self.source.close()
