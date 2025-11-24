import time
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

# ---------- CONFIG ----------
SAMPLE_RATE = 16000
CHANNELS = 1
DEFAULT_DURATION = 5.0  # seconds to record when called
MODEL_NAME = "tiny.en"  # or "base.en" if the Pi can handle it

# If your webcam mic isn't the default, set this:
# Find device index with: python -c "import sounddevice as sd; print(sd.query_devices())"
INPUT_DEVICE_INDEX = None  # e.g. 2
# ----------------------------

# Initialize the model once at import so other modules can reuse it.
print("[voice_recognizer] Loading Whisper model...")
model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
print("[voice_recognizer] Model loaded.")


def _record_audio(duration: float = DEFAULT_DURATION) -> np.ndarray:
    """Record audio from the default (or specified) input device."""
    if INPUT_DEVICE_INDEX is not None:
        sd.default.device = (INPUT_DEVICE_INDEX, None)

    num_samples = int(SAMPLE_RATE * duration)
    print(f"\n[record] Recording {duration:.1f} seconds... Speak now!")
    audio = sd.rec(
        num_samples,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
    )
    sd.wait()
    audio = audio.flatten()

    # Diagnostics: volume stats
    rms = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.max(np.abs(audio)))
    print(f"[record] Done. RMS: {rms:.4f}, Peak: {peak:.4f}")

    if peak < 0.01:
        print("[record] Warning: input level looks very low. Mic / gain issue?")

    return audio


def _transcribe_audio(audio: np.ndarray) -> str:
    """Run faster-whisper on a numpy audio array."""
    print("[whisper] Transcribing...")
    t0 = time.time()

    segments, info = model.transcribe(
        audio,
        beam_size=1,      # keep it light for Pi
        language="en",    # force English; set None for auto
        vad_filter=True,  # helps cut silence
    )

    dt = time.time() - t0
    print(
        f"[whisper] Done in {dt:.2f}s. "
        f"Detected language: {info.language} (p={info.language_probability:.2f})"
    )

    text = "".join(seg.text for seg in segments).strip()
    if not text:
        print("[whisper] No speech detected.")
    else:
        # Show segment-level diagnostics
        print("[whisper] Segments:")
        for seg in segments:
            print(
                f"  [{seg.start:5.2f}–{seg.end:5.2f}] "
                f"(p={seg.avg_logprob:.2f}, no_speech={seg.no_speech_prob:.2f}) {seg.text}"
            )

    return text


def listen_and_transcribe(duration: float = DEFAULT_DURATION) -> str:
    """
    High-level helper:
    - records for `duration` seconds
    - returns transcription string

    This is what you’ll typically import from your AI module.
    """
    audio = _record_audio(duration)
    text = _transcribe_audio(audio)
    print(f"[result] You said: {text!r}")
    return text


# Simple CLI loop so you can test it directly.
if __name__ == "__main__":
    try:
        while True:
            input("\nPress Enter to record, or Ctrl+C to quit...")
            listen_and_transcribe()
    except KeyboardInterrupt:
        print("\n[voice_recognizer] Goodbye.")
