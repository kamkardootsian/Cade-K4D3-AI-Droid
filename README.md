Cade (K4D3) – AI Droid Assistant
A Raspberry Pi–powered Star-Wars–style personal AI with voice interaction, TTS, vision, sensors, and modular tools

Cade (K4D3) is a fully voice-controlled personal AI droid built on a Raspberry Pi 5, combining:

Real-time wake-word detection

Whisper-based speech recognition

GPT-based conversational reasoning

Modular ACTION tools (sensor access, code inspection, system queries, etc.)

Text-to-speech output

A custom animated LCD “eye”

Motion sensors, webcam vision, and optional long-term memory

Systemd service auto-startup

A “Star-Wars-style” personality and UI

Cade is designed to run entirely on-device except for the model inference (OpenAI API).
Everything else—wake word, audio pipeline, sensors, camera capture, file I/O—is local.

✨ Features
🎤 Voice Interaction (Local)

Real-time microphone capture with RMS-based auto-start and auto-stop.

Faster-Whisper (tiny.en) for efficient transcription on the Pi 5.

Speech detection, trailing-silence detection, and recording limits.

Wake-word detection for:

“Cade”, “K4”, “K4D3”, “Kate”, etc.

Always-listening IDLE → ACTIVE state machine.

🧠 AI Backend (GPT)

GPT-style reasoning via ai_backend.py

Supports:

Non-streaming text responses

Streaming generation (planned voice-streaming)

Internal conversation history per session.

Short-term memory per session; optional long-term memory module.

🗣️ Text-to-Speech

OpenAI gpt-4o-mini-tts voice synthesis

WAV output played via aplay for ultra-low latency

Supports optional Piper TTS fallback (offline)

👁️ Vision Backend (Optional)

Webcam capture using OpenCV

GPT-assisted scene description:

“Describe what you see”

“Who is in front of you?”

Face-recognition ready (via dlib / face_recognition)

Future: person enrollment via folder of images

👁 Droid Eye Animation

Custom LCD screen eye with:

Idle animation

Thinking animation

Listening / speaking modes

Wake flash

Standby mode

🛠 ACTION Framework (Tool Calls)

Cade can choose between:

MODE:CHAT

Normal conversation.

MODE:ACT

Perform real-world actions such as:

CHECK_CODE → Read a local file and send it back through GPT

SET_VOLUME → Set amixer output volume on the Pi

GET_IP → Report internal network address

Extendable:

GET_SENSORS

GET_LOGS

DESCRIBE_SCENE

FACE_LOOKUP

Always responds in CHAT after the action completes.

🛰 Sensors

RCWL-0516 microwave Doppler radar (motion)

GPIO input/output expansion planned

Modular sensors_backend.py

🎛 System Integration

Runs as a systemd --user service

Optional Star-Wars-style log console

Volume auto-forcing scripts via amixer

Startup sound (Windows XP startup for now 😄)

📁 Project Structure
Droid/
│
├── cade_brain.py           # Main state machine & conversation loop
├── ai_backend.py           # GPT reasoning and streaming logic
├── tts_backend.py          # OpenAI TTS → WAV → aplay
├── voice_recognizer.py     # Whisper-based audio capture/transcription
├── vision_backend.py       # Webcam input and scene analysis (optional)
├── eye_engine.py           # LCD “eye” animations
├── sensors_backend.py      # Motion sensors / GPIO / RCWL-0516 integration
│
├── start_cade.sh           # Startup script for systemd
├── windowsxpstartup.wav    # Startup sound (replace with your own)
│
└── (venv)                  # Python virtual environment (ignored by git)

🚀 Setup
1. Clone the repo onto the Pi
git clone https://github.com/kamkardootsian/Cade-K4D3-AI-Droid.git
cd Cade-K4D3-AI-Droid

2. Create Python venv + install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

3. Add your OpenAI API key
echo "export OPENAI_API_KEY=your_key_here" >> ~/.bashrc
source ~/.bashrc

4. Enable as a systemd user service
systemctl --user enable cade.service
systemctl --user start cade.service


To view real-time logs:

journalctl --user-unit=cade.service -f

🧩 Usage

Say:

“Hey Cade…”

Examples:

“What’s the weather today?”

“Describe what you see.”

“Check your code for the vision module.”

“Set your volume to max.”

“I’m home.”

“Go to sleep.”

Cade responds with:

Eye animations

Spoken output

Intelligent ACTION calls when needed

🧱 Extending Cade
Add a new ACTION

In handle_action(...), add a new block:

if action_upper == "GET_SENSORS":
    ...


Implement the tool logic

Return a followup prompt to GPT

GPT auto-generates a natural-language CHAT response

Add long-term memory

Use a JSON-based approach and load it into the system prompt at session start.

Add local wake-word ML

Replace RMS-based wake detection with porcupine or vicuna-wake-light.

🎨 Screenshots / Demo

Coming soon.

🛡 License

MIT (or whatever you decide)

⭐ Contributing

Pull requests welcome — Cade is very modular and easy to extend.
