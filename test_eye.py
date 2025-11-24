#!/usr/bin/env python3
import time

from eye_engine import DroidEye

print("[test_eye] creating eye")
eye = DroidEye()
print("[test_eye] eye created, running wake_flash")

try:
    eye.wake_flash()
    time.sleep(1.0)

    print("[test_eye] running thinking animation")
    eye.thinking()
    time.sleep(0.5)

    print("[test_eye] done, shutting down eye")
    eye.shutdown()

except KeyboardInterrupt:
    print("[test_eye] interrupted, shutting down eye")
    eye.shutdown()

