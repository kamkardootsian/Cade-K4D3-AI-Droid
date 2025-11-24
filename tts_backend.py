"""
tts_backend.py

Text-to-speech backend for K4D3 ("Cade").

Primary:
    - OpenAI TTS (requires OPENAI_API_KEY)
    - Uses gpt-4o-mini-tts (or similar) to synthesize speech
    - Saves to a WAV file and plays it via `aplay` (ALSA) on Raspberry Pi

Fallback (optional):
    - Piper TTS via CLI, if installed and configured

Public function:
    speak(text: str) -> None
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from openai import OpenAI

# ---------- CONFIG ----------

# OpenAI TTS model & voice
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"  # adjust if needed
OPENAI_TTS_VOICE = "onyx"            # or another supported voice

# Playback command on Raspberry Pi
# aplay is usually available via: sudo apt-get install alsa-utils
PLAYBACK_CMD = ["aplay"]  # will append the filename at runtime

# Optional Piper fallback (if you install it later)
PIPER_ENABLED = False
PIPER_CMD = [
    "piper",
    "--model", "/path/to/your/piper-voice.onnx",  # replace later
    "--output_raw", "false",
    "--length_scale", "1.0",
    "--noise_scale", "0.667",
    "--noise_w", "0.8",
]
# ---------------------------


ROOT_DIR = Path(__file__).resolve().parent

# Use same env var as ai_backend
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


# ---------- UTILITIES ----------

def _play_wav(path: Path) -> None:
    """Play a WAV file using aplay (or another command if you customize)."""
    try:
        cmd = PLAYBACK_CMD + [str(path)]
        subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"[tts] Playback failed: {e}")

def _openai_tts_to_wav(text: str, out_path: Path) -> bool:
    """
    Use OpenAI TTS to synthesize `text` into a WAV file at `out_path`.
    Returns True on success, False otherwise.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[tts] OPENAI_API_KEY not set; cannot use OpenAI TTS.")
        return False

    try:
        print(f"[tts] Calling OpenAI TTS (model={OPENAI_TTS_MODEL}, voice={OPENAI_TTS_VOICE})...")

        response = client.audio.speech.create(
            model=OPENAI_TTS_MODEL,
            voice=OPENAI_TTS_VOICE,
            input=text,
            # 👇 THIS is the key bit:
            response_format="wav",
        )

        # You can keep using stream_to_file even with the warning;
        # it still writes the full file.
        response.stream_to_file(out_path)

        print(f"[tts] OpenAI TTS wrote WAV to {out_path}")
        return True

    except Exception as e:
        print(f"[tts] OpenAI TTS failed: {e}")
        return False



def _piper_tts_to_wav(text: str, out_path: Path) -> bool:
    """
    OPTIONAL: Piper TTS fallback.
    Requires piper + a voice model installed and PIPER_CMD configured correctly.
    """
    if not PIPER_ENABLED:
        return False

    try:
        print("[tts] Using Piper TTS fallback...")
        # We pipe the text into Piper's stdin and redirect output to a WAV
        # (Assumes Piper is configured to output WAV to stdout)
        with open(out_path, "wb") as wav_file:
            proc = subprocess.Popen(
                PIPER_CMD,
                stdin=subprocess.PIPE,
                stdout=wav_file,
                stderr=subprocess.PIPE,
            )
            stdout_data, stderr_data = proc.communicate(input=text.encode("utf-8"))

        if proc.returncode != 0:
            print(f"[tts] Piper failed: {stderr_data.decode('utf-8', errors='ignore')}")
            return False

        print(f"[tts] Piper wrote WAV to {out_path}")
        return True
    except Exception as e:
        print(f"[tts] Piper TTS failed: {e}")
        return False


# ---------- PUBLIC API ----------

def speak(text: str, max_chars: int = 500) -> None:
    """
    Convert `text` to speech and play it through the Pi's speakers.

    - Truncates very long text for TTS sanity.
    - Tries OpenAI TTS first; if that fails and Piper is enabled, tries Piper.
    """
    text = (text or "").strip()
    if not text:
        print("[tts] Empty text, nothing to speak.")
        return

    if len(text) > max_chars:
        print(f"[tts] Truncating text from {len(text)} to {max_chars} chars for TTS.")
        text = text[:max_chars]

    # Temporary file for WAV output
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = Path(tmp.name)

    # 1) Try OpenAI TTS
    ok = _openai_tts_to_wav(text, out_path)

    # 2) If OpenAI fails, optionally try Piper
    if not ok:
        ok = _piper_tts_to_wav(text, out_path)

    if not ok:
        print("[tts] All TTS methods failed; Cade will be silent for this reply.")
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass
        return

    # 3) Play the WAV
    _play_wav(out_path)

    # 4) Cleanup
    try:
        out_path.unlink(missing_ok=True)
    except Exception:
        pass


if __name__ == "__main__":
    # Simple CLI test: python tts_backend.py "hello there"
    import sys
    test_text = " ".join(sys.argv[1:]) or "Hello, I am Cade."
    speak(test_text)

