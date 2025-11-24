"""
cade_brain.py

Conversation / state machine layer for K4D3 ("Cade").

Responsibilities:
- IDLE state: wait for a wake word ("K4", "K4D3", "Cade", etc.)
- When woken, create a new conversation history via ai_backend.new_history()
- ACTIVE state: carry on a back-and-forth conversation using ai_backend.generate_response()
- Detect shutdown phrases ("shut down", "thank you", "goodbye", etc.) and
  return to IDLE when heard.

Audio input is handled by voice_recognizer.listen_and_transcribe_auto(),
which:
- waits for you to start talking
- stops after trailing silence
- returns one utterance as text
"""

from __future__ import annotations

import re
import time                     # ?? add this
from typing import List, Dict

from voice_recognizer import listen_and_transcribe_auto
from ai_backend import new_history, generate_response  # implemented in ai_backend.py

from tts_backend import speak
import subprocess
import os
import shutil
import random
import socket

from eye_engine import DroidEye   # ?? add this

def get_internal_ip():
    """Return the Pi's internal LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Doesn't need to be reachable — just forces OS to pick the right adapter
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Unknown"


# --------- CONFIG: wake words & shutdown phrases ---------

# All the ways you might say the assistant's name
WAKE_WORDS = [
    "k4",
    "k 4",
    "k4d3",
    "k4 d3",
    "cade",
    "kade",
    "kayde",
    "kadee",
    "kate"
]

# Phrases that end an active conversation session
SHUTDOWN_PHRASES = [
    "shutdown",
    "go to sleep",
    "you can sleep",
    "stand by",
    "standby",
    "that'll be all",
    "that will be all",
    "goodbye",
    "good bye",
    "bye cade",
    "bye kate",
    "bye kade",
    "see you later"
]
THINKING_PHRASES = [
    "Hmm...",
    ""
]

def quick_thinking_ack(eye=None):
    """Short filler while we spin up the real response."""
    phrase = random.choice(THINKING_PHRASES)
    if eye:
        # quick little flicker so it feels alive
        eye.thinking(cycles=3)
    speak(phrase)

def play_sound(path: str) -> None:
    """
    Play a WAV file using aplay (most reliable on Raspberry Pi).
    aplay does NOT support MP3, so file must be .wav.
    """
    # Confirm file exists
    if not os.path.exists(path):
        print(f"[play_sound] File not found: {path}")
        return

    # Confirm aplay is installed
    if not shutil.which("aplay"):
        print("[play_sound] 'aplay' not found. Install with: sudo apt install alsa-utils")
        return

    try:
        subprocess.Popen(
            ["aplay", "-q", path],   # -q makes it quiet (no ALSA spam)
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"[play_sound] Playing {path} with aplay")
    except Exception as e:
        print(f"[play_sound] Failed to play {path}: {e}")

# --------- TEXT NORMALIZATION HELPERS ---------

def normalize(text: str) -> str:
    """
    Normalize text for matching:
    - lowercase
    - strip non alphanumerics to spaces
    - collapse multiple spaces
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def has_wake_word(text: str) -> bool:
    """
    Returns True if the utterance contains a wake word.

    This is intentionally a bit permissive so that:
    - "cade"
    - "hey cade"
    - "okay k4d3"
    - "yo k4, what's up"
    all count.
    """
    norm = normalize(text)
    if not norm:
        return False

    padded = f" {norm} "
    for ww in WAKE_WORDS:
        ww_norm = normalize(ww)
        if ww_norm == "":
            continue

        # exact match: "cade"
        if norm == ww_norm:
            return True

        # at start: "cade what's the weather"
        if norm.startswith(ww_norm + " "):
            return True

        # in middle: "hey cade what's up"
        if f" {ww_norm} " in padded:
            return True

    return False

def strip_wake_word(text: str) -> str:
    """
    Remove the FIRST occurrence of a wake word and return ONLY what comes
    *after* it in the utterance.

    Examples (normalized):
        "cade what's the weather"        -> "what's the weather"
        "hey cade what's up"             -> "what's up"
        "okay k4d3 tell me a joke"       -> "tell me a joke"
        "cade"                           -> ""
    """
    norm = normalize(text)
    if not norm:
        return ""

    padded = f" {norm} "

    for ww in WAKE_WORDS:
        ww_norm = normalize(ww)
        if not ww_norm:
            continue

        marker = f" {ww_norm} "
        idx = padded.find(marker)
        if idx != -1:
            # everything AFTER the wake word
            after = padded[idx + len(marker):].strip()
            return after

    # no wake word found, just return normalized text
    return norm


def is_shutdown(text: str) -> bool:
    """
    True if this utterance should end the ACTIVE session and return to IDLE.
    """
    norm = normalize(text)
    if not norm:
        return False

    for phrase in SHUTDOWN_PHRASES:
        phrase_norm = normalize(phrase)
        if phrase_norm and phrase_norm in norm:
            return True

    return False


# --------- MAIN CONVERSATION LOOP ---------

def cade_loop() -> None:
    print("Cade is online. Say its name to wake it up.")

    # ?? Try to bring up the eye, but don't die if it fails
    eye = None
    if DroidEye is not None:
        try:
            eye = DroidEye()
            print("[eye] DroidEye initialized.")
            eye.idle()
        except Exception as e:
            print(f"[eye] Failed to init DroidEye: {e}")
            eye = None
    else:
        print("[eye] DroidEye class not available; running headless.")

    # ?? Play startup sound once on boot
    startup_sound = os.path.join(os.path.dirname(__file__), "windowsxpstartup.wav")
    print(f"[main] Startup sound path: {startup_sound}")
    play_sound(startup_sound)

    while True:
        # -------- IDLE STATE --------
        print("\n[STATE] IDLE waiting for wake word...")
        if eye:
            eye.idle()

        utterance = listen_and_transcribe_auto()
        if not utterance:
            continue

        print(f"[IDLE] Heard: {utterance!r}")

        if not has_wake_word(utterance):
            print("[wake] No wake word detected (ignoring).")
            continue

        # Visual: wake flash
        if eye:
            eye.wake_flash()

        command = strip_wake_word(utterance)
        print(f"[wake] Wake word detected. Initial command after strip: {command!r}")

        history = new_history()

        # Eye: active listening posture
        if eye:
            eye.listening()

        # -------- FIRST RESPONSE --------
        if command:
            if eye:
                eye.thinking()
            reply = generate_response(history, command)
            print(f"Cade: {reply}")
            if eye:
                eye.speaking()
            speak(reply)
        else:
            reply = "I'm here. What can I do for you?"
            print(f"Cade: {reply}")
            if eye:
                eye.speaking()
            speak(reply)

        # Back to active listening glow
        if eye:
            eye.listening()

        # -------- ACTIVE STATE --------
        active = True
        while active:
            print("\n[STATE] ACTIVE listening for next instruction...")
            if eye:
                eye.listening()

            user_utterance = listen_and_transcribe_auto()
            if not user_utterance:
                continue

            print(f"[ACTIVE] Heard: {user_utterance!r}")

            if "your internal ip" in user_utterance.lower() or "your local ip" in user_utterance.lower():
                ip = get_internal_ip()
                reply = f"My internal IP address is {ip}."
                speak(reply)
                continue


            if is_shutdown(user_utterance):
                print("Cade: Okay, shutting down. Thank you.")
                if eye:
                    eye.standby()
                speak("Okay, going into standby mode")
                active = False
                break

            if has_wake_word(user_utterance):
                user_utterance = strip_wake_word(user_utterance)
                print(f"[ACTIVE] Wake word stripped mid-session: {user_utterance!r}")
                if not user_utterance:
                    continue

            if not user_utterance:
                continue

            if eye:
                eye.thinking()
            if len(user_utterance.split()) > 4:
                quick_thinking_ack(eye)
            
            reply = generate_response(history, user_utterance)
            print(f"Cade: {reply}")
            if eye:
                eye.speaking()
            speak(reply)

            # Back to listening glow for next turn
            if eye:
                eye.listening()


if __name__ == "__main__":
    try:
        cade_loop()
    except KeyboardInterrupt:
        print("\n[main] Interrupted, exiting.")
