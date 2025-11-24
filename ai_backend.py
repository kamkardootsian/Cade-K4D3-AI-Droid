# ai_backend.py
#
# Backend for K4D3 ("Cade"):
# - Uses OpenAI API for responses
# - Loads primary system prompt from cade_system_prompt.txt
# - Maintains per-session chat history
# - Provides a simple file-based long-term memory system
#   via cade_memory.json and helper functions.

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Iterator

from openai import OpenAI

# ---------- PATHS & CONFIG ----------

ROOT_DIR = Path(__file__).resolve().parent
PROMPT_FILE = ROOT_DIR / "cade_system_prompt.txt"
MEMORY_FILE = ROOT_DIR / "cade_memory.json"

# Models
CHAT_MODEL = "gpt-4.1-mini"       # main conversation model
SUMMARIZER_MODEL = "gpt-4.1-mini" # can be same or smaller

# History / memory limits (tweak as you like)
MAX_HISTORY_MESSAGES = 24   # per session (not counting system)
MAX_MEMORY_ITEMS = 60       # total long-term memory chunks
TARGET_MEMORY_ITEMS = 40    # after pruning/summarizing, aim for about this many

# ---------- OPENAI CLIENT ----------

# Uses OPENAI_API_KEY from environment.
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)


# ---------- TYPES ----------

Message = Dict[str, str]           # {"role": "system"/"user"/"assistant", "content": str}
History = List[Message]
MemoryItem = Dict[str, Any]        # {"text": str, "created_at": float, "source": str, "importance": int}


# ---------- SYSTEM PROMPT LOADING ----------

def _load_system_prompt() -> str:
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8").strip()
    # Fallback default if file missing
    return (
        "You are K4D3 (“Cade”), a friendly, concise voice assistant. "
        "Keep replies short and natural, suitable for speaking aloud."
    )


# ---------- LONG-TERM MEMORY STORAGE ----------

def _load_memory() -> List[MemoryItem]:
    if not MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _save_memory(memories: List[MemoryItem]) -> None:
    MEMORY_FILE.write_text(json.dumps(memories, indent=2), encoding="utf-8")


def _memory_as_bullets(memories: List[MemoryItem]) -> str:
    if not memories:
        return "No prior memories."
    lines = [f"- {m['text']}" for m in memories]
    return "\n".join(lines)


# ---------- HISTORY CONSTRUCTION ----------

def new_history() -> History:
    """
    Create a fresh history for a new ACTIVE session.

    - Loads the base system prompt
    - Loads long-term memory items from disk
    - Injects them into a single system message
    """
    base_prompt = _load_system_prompt()
    memories = _load_memory()

    # Keep only the most recent N memories
    memories_sorted = sorted(memories, key=lambda m: m.get("created_at", 0), reverse=True)
    recent_memories = memories_sorted[:20]  # you can tweak this

    memory_text = _memory_as_bullets(recent_memories)

    system_content = (
        f"{base_prompt}\n\n"
        "You also have some remembered facts and summaries about the user and past interactions.\n"
        "Use them when relevant, but do not hallucinate additional details.\n\n"
        "Memories:\n"
        f"{memory_text}"
    )

    history: History = [
        {"role": "system", "content": system_content}
    ]
    return history


# ---------- HISTORY TRIMMING ----------

def _trim_history_inplace(history: History) -> None:
    """
    Keep the system message + last N user/assistant messages.
    Mutates the history list in place.
    """
    if len(history) <= MAX_HISTORY_MESSAGES + 1:
        return

    system_msg = history[0]
    tail = history[1:]
    tail = tail[-MAX_HISTORY_MESSAGES:]
    history.clear()
    history.append(system_msg)
    history.extend(tail)


# ---------- MAIN CHAT COMPLETION ----------

def generate_response(history: History, user_text: str) -> str:
    """
    Append a user message, call the OpenAI chat model, append assistant reply,
    and return the reply text.
    """
    if not user_text:
        return ""

    history.append({"role": "user", "content": user_text})
    _trim_history_inplace(history)

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=history,
    )

    reply = response.choices[0].message.content or ""
    history.append({"role": "assistant", "content": reply})
    return reply

def generate_response_streaming(history: History, user_text: str) -> Iterator[str]:
    """
    Streaming version of generate_response.

    - Appends the user message to history
    - Calls the OpenAI chat model with stream=True
    - Yields text chunks as they arrive
    - After the stream finishes, appends the full assistant reply to history

    Usage pattern (in cade_brain.py, for example):

        full_reply = ""
        for chunk in generate_response_streaming(history, user_text):
            full_reply += chunk
            # send `chunk` to TTS here

        # `history` now includes the assistant's full reply
    """
    if not user_text:
        return
        yield  # makes this a generator even if we early-return

    # Add the new user message
    history.append({"role": "user", "content": user_text})
    _trim_history_inplace(history)

    # Call OpenAI with streaming enabled
    stream = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=history,
        stream=True,
    )

    full_reply_parts: List[str] = []

    for chunk in stream:
        # Each chunk contains a delta with optional content
        choice = chunk.choices[0]
        delta = choice.delta

        # In the new OpenAI python client, delta.content is usually a string (or None)
        token = getattr(delta, "content", None)
        if not token:
            continue

        full_reply_parts.append(token)
        # Yield this token to the caller (cade_brain) immediately
        yield token

    # After streaming is done, join everything and append to history
    full_reply = "".join(full_reply_parts).strip()
    if full_reply:
        history.append({"role": "assistant", "content": full_reply})


# ---------- MEMORY EXTRACTION / PRUNING ----------

def extract_memories_from_history(history: History, max_new: int = 5) -> List[str]:
    """
    Ask the model to extract important, reusable "memories" from the conversation.

    Returns a list of strings, each a short memory like:
      - "User lives in Torrance, California."
      - "User prefers responses in Japanese with furigana."
    """
    # Don’t include the initial system message, just the dialog
    dialog = history[1:]

    # Build a prompt for summarization / memory extraction
    system = (
        "You are a memory extraction module for a voice assistant.\n"
        "Given a conversation, identify up to a few concise, durable facts or preferences "
        "about the user or ongoing long-term projects.\n"
        "Only include items that would be useful in future conversations (e.g., preferences, "
        "personality, stable facts). Skip small talk and fleeting details.\n"
        f"Return ONLY a JSON list of strings, no extra text.\n"
        f"Limit to at most {max_new} items."
    )

    # Flatten dialog messages into one plain-text transcript
    lines = []
    for m in dialog:
        role = m["role"]
        prefix = "User" if role == "user" else "Assistant" if role == "assistant" else "System"
        lines.append(f"{prefix}: {m['content']}")
    transcript = "\n".join(lines)

    messages: History = [
        {"role": "system", "content": system},
        {"role": "user", "content": transcript},
    ]

    resp = client.chat.completions.create(
        model=SUMMARIZER_MODEL,
        messages=messages,
        temperature=0.2,
    )

    raw = resp.choices[0].message.content or "[]"

    try:
        memories = json.loads(raw)
        if isinstance(memories, list):
            return [str(x).strip() for x in memories if str(x).strip()]
    except Exception:
        # If the model didn't follow instructions, just bail quietly
        pass

    return []


def update_long_term_memory_from_history(history: History, source: str = "conversation") -> None:
    """
    Call this *after* a session ends (e.g., when Cade hears 'shut down').

    - Extracts a few new memories from the history
    - Appends them to cade_memory.json with metadata
    - If memory gets too large, asks the model to summarize/prune
    """
    existing = _load_memory()
    new_memory_texts = extract_memories_from_history(history)

    if not new_memory_texts:
        return

    now = time.time()
    for text in new_memory_texts:
        existing.append(
            {
                "text": text,
                "created_at": now,
                "source": source,
                "importance": 1,  # simple placeholder; could be scored later
            }
        )

    # If we exceed the max, prune/summarize
    if len(existing) > MAX_MEMORY_ITEMS:
        existing = _prune_and_summarize_memories(existing)

    _save_memory(existing)


def _prune_and_summarize_memories(memories: List[MemoryItem]) -> List[MemoryItem]:
    """
    When memory is too large, we:
    - Send all memory texts to the model
    - Ask for a tighter set of summarized bullet points
    - Replace the memory store with that new reduced list.
    """
    memory_texts = [m["text"] for m in memories]

    system = (
        "You are a memory compression module for a voice assistant.\n"
        "You receive a list of many memory bullet points about the user.\n"
        "Some may be redundant or overly specific.\n"
        f"Condense and merge them into at most {TARGET_MEMORY_ITEMS} bullet points that preserve "
        "all important long-term facts and preferences.\n"
        "Return ONLY a JSON list of strings, no extra commentary."
    )

    user_content = json.dumps(memory_texts, ensure_ascii=False, indent=2)

    messages: History = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    resp = client.chat.completions.create(
        model=SUMMARIZER_MODEL,
        messages=messages,
        temperature=0.2,
    )

    raw = resp.choices[0].message.content or "[]"

    try:
        compressed = json.loads(raw)
        if not isinstance(compressed, list):
            raise ValueError("Not a list")

        now = time.time()
        new_memories: List[MemoryItem] = []
        for text in compressed:
            text = str(text).strip()
            if not text:
                continue
            new_memories.append(
                {
                    "text": text,
                    "created_at": now,
                    "source": "summary",
                    "importance": 1,
                }
            )
        return new_memories
    except Exception:
        # If summarization fails, fall back to the most recent items
        memories_sorted = sorted(memories, key=lambda m: m.get("created_at", 0), reverse=True)
        return memories_sorted[:TARGET_MEMORY_ITEMS]

