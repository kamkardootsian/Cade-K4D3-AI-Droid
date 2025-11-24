# voice_recognizer.py

import time
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
import contextlib
import os

# ---------- CONFIG ----------
SAMPLE_RATE = 16000
CHANNELS = 1

MODEL_NAME = "tiny.en"  # or "base.en" etc. if Pi 5 can handle it

# Audio device; set to an index from sd.query_devices() if needed
INPUT_DEVICE_INDEX = 0  # e.g. 2

# VAD-ish settings
BLOCK_DURATION = 0.2       # seconds per audio chunk
SILENCE_THRESHOLD = 0.008   # RMS below this = "silence"
MIN_SPEECH_DURATION = 0.5  # must have at least this much voiced audio
TRAILING_SILENCE = 0.5     # stop after this much silence *after* speech
MAX_RECORD_TIME = 15.0     # safety upper bound in seconds
# ----------------------------

print("[voice_recognizer] Loading Whisper model...")
model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
print("[voice_recognizer] Model loaded.")

def _open_input_stream_for_device(dev_index: int):
    """
    Try to open an InputStream on the given device with a handful
    of candidate sample rates and channel counts. Returns
    (stream, device_sr, channels) on success, or (None, None, None) on failure.
    """
    # Common sane rates to try. Adjust or reorder if needed.
    candidate_rates = [48000, 16000, 44100]
    candidate_channels = [1, 2]

    last_error = None

    for sr in candidate_rates:
        for ch in candidate_channels:
            block_size = int(sr * BLOCK_DURATION)
            try:
                with open(os.devnull, "w") as devnull, contextlib.redirect_stderr(devnull):
                    stream = sd.InputStream(
                        device=dev_index,
                        samplerate=sr,
                        channels=ch,
                        dtype="float32",
                        blocksize=block_size,
                    )
                print(f"[record] Opened input device {dev_index} @ {sr} Hz, {ch}ch")
                return stream, sr, ch
            except sd.PortAudioError as e:
                last_error = e
                # Try the next combo
                continue

    print(f"[record] Failed to open device {dev_index} with all candidate sample rates.")
    if last_error is not None:
        print(f"[record] Last PortAudioError: {last_error}")
    return None, None, None


def _get_input_device_and_rate():
    """Return (device_index, samplerate) for the chosen input device."""
    if INPUT_DEVICE_INDEX is not None:
        dev_index = INPUT_DEVICE_INDEX
    else:
        dev_index = sd.default.device[0]  # current default input

    info = sd.query_devices(dev_index, 'input')
    sr = int(info['default_samplerate'])
    print(f"[record] Using input device {dev_index} @ {sr} Hz")
    return dev_index, sr


def _resample_to_16k(audio: np.ndarray, orig_sr: int, target_sr: int = SAMPLE_RATE) -> np.ndarray:
    """Very simple linear resample using numpy (no SciPy needed)."""
    if audio.size == 0 or orig_sr == target_sr:
        return audio

    import numpy as np
    duration = len(audio) / orig_sr
    new_len = int(round(duration * target_sr))
    if new_len <= 0:
        return np.zeros(0, dtype="float32")

    t_old = np.linspace(0.0, duration, num=len(audio), endpoint=False)
    t_new = np.linspace(0.0, duration, num=new_len, endpoint=False)
    resampled = np.interp(t_new, t_old, audio).astype("float32")
    return resampled
    

def _record_until_silence() -> np.ndarray:
    """
    Listen on the mic and automatically:
    - start when sound passes SILENCE_THRESHOLD
    - stop after TRAILING_SILENCE seconds of low input
    - or after MAX_RECORD_TIME
    Returns: mono float32 numpy array at SAMPLE_RATE (16 kHz) for Whisper.
    """
    dev_index = INPUT_DEVICE_INDEX if INPUT_DEVICE_INDEX is not None else sd.default.device[0]

    stream, device_sr, actual_channels = _open_input_stream_for_device(dev_index)
    if stream is None:
        # Could not open the device at any sane rate; bail for this cycle
        return np.zeros(0, dtype="float32")

    block_size = int(device_sr * BLOCK_DURATION)
    chunks = []

    speech_started = False
    start_time = time.time()
    last_voice_time = None

    print("\n[record] Waiting for speech...")

    def rms(x: np.ndarray) -> float:
        return float(np.sqrt(np.mean(x ** 2))) if x.size > 0 else 0.0

    try:
        with stream:
            while True:
                if time.time() - start_time > MAX_RECORD_TIME:
                    print("[record] Hit MAX_RECORD_TIME, stopping.")
                    break

                block, overflowed = stream.read(block_size)
                if overflowed:
                    print("[record] Warning: buffer overflowed.")

                # Downmix to mono if needed
                mono = block.mean(axis=1) if block.ndim > 1 else block.flatten()
                level = rms(mono)

                if not speech_started:
                    if level > SILENCE_THRESHOLD:
                        speech_started = True
                        last_voice_time = time.time()
                        print("[record] Speech detected, recording...")
                        chunks.append(mono)
                else:
                    chunks.append(mono)

                    if level > SILENCE_THRESHOLD:
                        last_voice_time = time.time()
                    else:
                        if last_voice_time is not None:
                            silence_time = time.time() - last_voice_time
                            if silence_time >= TRAILING_SILENCE:
                                print(
                                    f"[record] Trailing silence ({silence_time:.2f}s) reached, stopping."
                                )
                                break

    except sd.PortAudioError as e:
        print(f"[record] PortAudioError during recording: {e}")
        return np.zeros(0, dtype="float32")

    if not chunks:
        print("[record] No speech captured.")
        return np.zeros(0, dtype="float32")

    audio = np.concatenate(chunks)
    duration = len(audio) / device_sr
    print(f"[record] Captured {duration:.2f}s of audio at {device_sr} Hz.")

    if duration < MIN_SPEECH_DURATION:
        print("[record] Too short to be real speech, discarding.")
        return np.zeros(0, dtype="float32")

    overall_rms = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.max(np.abs(audio)))
    print(f"[record] RMS: {overall_rms:.4f}, Peak: {peak:.4f}")
    if peak < 0.01:
        print("[record] Warning: input level looks very low.")

    # Resample to 16 kHz for Whisper
    audio_16k = _resample_to_16k(audio, device_sr, SAMPLE_RATE)
    return audio_16k



def _transcribe_audio(audio: np.ndarray) -> str:
    """Run faster-whisper on a numpy audio array."""
    if audio.size == 0:
        return ""

    print("[whisper] Transcribing...")
    t0 = time.time()

    segments, info = model.transcribe(
        audio,
        beam_size=1,
        language="en",
        vad_filter=True,
        initial_prompt=(
        "The robot's name is k4d3, known as k4 or Cade. "
        "The user will often say the word 'Cade' or 'k4' clearly. "
        "Prefer transcribing similar sounds (like 'cade', 'kade', 'k4', 'k4d3', 'kate') as 'Cade'. "
        "The robot only responds when it hears its name."
        )
)


    dt = time.time() - t0
    print(
        f"[whisper] Done in {dt:.2f}s. "
        f"Detected language: {info.language} (p={info.language_probability:.2f})"
    )

    text = "".join(seg.text for seg in segments).strip()

    if not text:
        print("[whisper] No speech detected by model.")
    else:
        print("[whisper] Segments:")
        for seg in segments:
            print(
                f"  [{seg.start:5.2f}–{seg.end:5.2f}] "
                f"(p={seg.avg_logprob:.2f}, no_speech={seg.no_speech_prob:.2f}) {seg.text}"
            )

    return text


def listen_and_transcribe_auto() -> str:
    """
    - waits for you to start talking
    - stops after you pause
    - returns transcription string
    """
    audio = _record_until_silence()
    if audio.size == 0:
        print("[result] Nothing to transcribe.")
        return ""

    text = _transcribe_audio(audio)
    print(f"[result] You said: {text!r}")
    return text


if __name__ == "__main__":
    # Basic test mode
    try:
        while True:
            input("\nPress Enter, then speak...")
            listen_and_transcribe_auto()
    except KeyboardInterrupt:
        print("\n[voice_recognizer] Goodbye.")
