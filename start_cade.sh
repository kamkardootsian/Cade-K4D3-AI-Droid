#!/bin/bash

#force WM8960 volume to max

amixer -c 2 sset 'Speaker' 100% unmute || true
amixer -c 2 sset 'Headphone' 100% unmute || true

# Activate venv and run Cade
cd /home/seanakutagawa/Droid
source venv/bin/activate
exec python -u cade_brain.py

