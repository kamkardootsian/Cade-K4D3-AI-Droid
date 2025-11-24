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


import json
from pathlib import Path

import re
from typing import List, Dict
from vision_backend import describe_scene
from voice_recognizer import listen_and_transcribe_auto
from ai_backend import new_history, generate_response, generate_response_streaming

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
    return
#    phrase = random.choice(THINKING_PHRASES)
#    if eye:
        # quick little flicker so it feels alive
#        eye.thinking(cycles=3)
#    speak(phrase)

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

def get_streamed_reply(history, user_text: str) -> str:
    """
    Convenience wrapper around generate_response_streaming:
    - Iterates all chunks
    - Concatenates them into one string
    - Returns the full reply

    Right now we still call TTS once on the full reply, but this sets you up to
    later stream chunks into a streaming TTS backend instead of buffering.
    """
    full_reply = ""
    for chunk in generate_response_streaming(history, user_text):
        full_reply += chunk
        # In the future: send `chunk` to a streaming TTS engine here
    return full_reply

def parse_model_reply(content: str):
    """
    Parse the model reply into:
    - mode: "CHAT" or "ACT"
    - action: str or None
    - args: dict or None
    - chat_text: str or None

    Expected formats:

    MODE:CHAT
    <text to speak>

    or

    MODE:ACT
    ACTION:<ACTION_NAME>
    ARGS:<JSON>
    """
    if not content:
        return "CHAT", None, None, ""

    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines:
        return "CHAT", None, None, ""

    first = lines[0].upper()
    # Default fallback
    if not first.startswith("MODE:"):
        return "CHAT", None, None, content

    if first.startswith("MODE:CHAT"):
        chat_text = "\n".join(lines[1:]).strip()
        if not chat_text:
            chat_text = ""  # avoid None
        return "CHAT", None, None, chat_text

    if first.startswith("MODE:ACT"):
        action = None
        args = {}
        for line in lines[1:]:
            if line.upper().startswith("ACTION:"):
                action = line.split(":", 1)[1].strip()
            elif line.upper().startswith("ARGS:"):
                arg_str = line.split(":", 1)[1].strip()
                try:
                    args = json.loads(arg_str) if arg_str else {}
                except Exception as e:
                    print(f"[parse_model_reply] Failed to parse ARGS JSON: {e}")
                    args = {}
        return "ACT", action, args, None

    # Unknown mode -> treat as normal chat
    return "CHAT", None, None, content
    
def handle_action(action: str | None,
                  args: Dict | None,
                  history,
                  user_text: str,
                  eye: DroidEye | None):
    """
    Handle MODE:ACT frames.

    - Reads a file
    - Sends its contents back through the model as a follow-up
    - Speaks the final result

    add more actions here (GET_SENSORS, GET_LOGS, etc.).
    """
    if not action:
        print("[handle_action] No ACTION provided, ignoring.")
        return

    args = args or {}
    action_upper = action.upper()
    print(f"[handle_action] ACTION={action_upper}, ARGS={args}")

    if action_upper == "CHECK_CODE":
        file_path = args.get("file", "cade_brain.py")
        try:
            path = Path(file_path)
            if not path.exists():
                tool_result = f"[CHECK_CODE] File not found: {file_path}"
            else:
                code = path.read_text(encoding="utf-8", errors="ignore")
                # You could summarize or analyze locally here;
                # for now we just forward the code back to the model.
                tool_result = (
                    f"Here is the current content of {file_path}:\n\n"
                    f"{code}"
                )
        except Exception as e:
            tool_result = f"[CHECK_CODE] Error reading {file_path}: {e}"

        # Second call: give the model the tool result and ask it to respond to the user.
        followup_prompt = (
            "You previously requested ACTION:CHECK_CODE.\n"
            f"The file contents are below:\n\n{tool_result}\n\n"
            f"The user originally said: {user_text}\n\n"
            "Now respond to the user in CHAT mode."
        )
        if eye:
            eye.thinking()
        followup_reply = get_streamed_reply(history, followup_prompt)
        print(f"Cade (follow-up): {followup_reply}")
        handle_model_reply(history, user_text, followup_reply, eye)
        return
    if action_upper == "SEE":
        try:
            desc = describe_scene()
            tool_result = f"The camera sees: {desc}"
        except Exception as e:
            tool_result = f"[SEE] Error using camera: {e}"

        followup_prompt = (
            "You previously requested ACTION:SEE.\n"
            f"Vision result: {tool_result}\n\n"
            f"The user originally said: {user_text}\n\n"
            "Now respond to the user in CHAT mode, briefly."
        )

    if eye:
        eye.thinking()

    followup_reply = get_streamed_reply(history, followup_prompt)
    print(f"Cade (follow-up): {followup_reply}")
    handle_model_reply(history, user_text, followup_reply, eye)
    return

    # Unknown action: just tell the user we don't handle it yet.
    fallback = f"I tried to perform an action called '{action}', but I don't know how to handle that yet."
    print(f"[handle_action] Unknown action '{action}', falling back to chat.")
    if eye:
        eye.speaking()
    speak(fallback)
    
def handle_model_reply(history,
                       user_text: str,
                       reply: str,
                       eye: DroidEye | None):
    """
    Central place to interpret the model reply and decide whether to:
    - speak it (MODE:CHAT)
    - run an internal action (MODE:ACT)
    """
    mode, action, args, chat_text = parse_model_reply(reply)
    print(f"[handle_model_reply] mode={mode}, action={action}, args={args}")

    if mode == "ACT":
        # Do NOT send anything to TTS yet; run the action pipeline instead
        handle_action(action, args, history, user_text, eye)
        return

    # Default / MODE:CHAT
    text_to_speak = chat_text if chat_text is not None else reply
    if not text_to_speak:
        text_to_speak = "I'm not sure what to say."

    print(f"Cade: {text_to_speak}")
    if eye:
        eye.speaking()
    speak(text_to_speak)
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
            # Stream the model response and join chunks
            reply = get_streamed_reply(history, command)
            handle_model_reply(history, command, reply, eye)
        else:
            # No explicit command after wake word
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

            # Streamed reply
            reply = get_streamed_reply(history, user_utterance)
            handle_model_reply(history, user_utterance, reply, eye)

            # Back to listening glow for next turn
            if eye:
                eye.listening()


if __name__ == "__main__":
    try:
        cade_loop()
    except KeyboardInterrupt:
        print("\n[main] Interrupted, exiting.")
