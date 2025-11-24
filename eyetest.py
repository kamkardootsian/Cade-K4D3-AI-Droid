#!/usr/bin/python3
# -*- coding:utf-8 -*-

import time
import math
import os
import sys
from PIL import Image, ImageDraw

# --- IMPORTANT: point to your Waveshare LCD driver location ---
LCD_PROJECT_PATH = "/home/seanakutagawa/LCD_Module_RPI_code/RaspberryPi/python"

if LCD_PROJECT_PATH not in sys.path:
    sys.path.append(LCD_PROJECT_PATH)

from lib import LCD_2inch4

class DroidEye:
    def __init__(self):
        # Init LCD
        self.disp = LCD_2inch4.LCD_2inch4()
        try:
            self.disp.Init()
        except TypeError:
            self.disp.Init(LCD_2inch4.SCAN_DIR_DFT)
        self.disp.clear()

        # 🔥 Turn backlight ON (0–100)
        try:
            if hasattr(self.disp, "bl_DutyCycle"):
                self.disp.bl_DutyCycle(100)
            elif hasattr(self.disp, "BL_DutyCycle"):
                self.disp.BL_DutyCycle(100)
            else:
                print("[eye] No bl_DutyCycle method found on LCD_2inch4")
        except Exception as e:
            print("[eye] Could not set backlight duty cycle:", e)

        self.width = self.disp.width
        self.height = self.disp.height
        self.cx = self.width // 2
        self.cy = self.height // 2
        self.radius = min(self.width, self.height) // 3

        self.running = True

    # ------------------------------------------------------------------

    def _draw_eye(self, x_offset=0, y_offset=0, brightness=255):
        img = Image.new("RGB", (self.width, self.height), "white")
        self.disp.ShowImage(img)

    # ------------------------------------------------------------------
    # MODES
    # ------------------------------------------------------------------

    def idle(self):
        """Slow breathing glow"""
        t = 0
        while self.running:
            brightness = int(150 + 80 * math.sin(t))
            self._draw_eye(brightness=brightness)
            t += 0.1
            time.sleep(0.05)

    def wake_flash(self):
        """Flash the eye bright once when wake word is detected"""
        for i in range(3):
            self._draw_eye(brightness=255)
            time.sleep(0.07)
            self._draw_eye(brightness=80)
            time.sleep(0.07)

    def listening(self):
        """Eye looks slightly left/right as if focusing"""
        offsets = [-30, 0, 30, 0]
        for off in offsets:
            self._draw_eye(x_offset=off, brightness=255)
            time.sleep(0.15)

    def thinking(self):
        """Fast pulse (AI thinking)"""
        t = 0
        for _ in range(40):   # lasts ~2 seconds
            brightness = int(120 + 100 * math.sin(t * 3))
            self._draw_eye(brightness=brightness)
            t += 0.1
            time.sleep(0.04)

    def speaking(self):
        """Gentle steady glow"""
        for _ in range(25):
            self._draw_eye(brightness=200)
            time.sleep(0.05)

    def shutdown(self):
        """Shrink eye into nothing"""
        for r in range(self.radius, 0, -4):
            img = Image.new("RGB", (self.width, self.height), "black")
            draw = ImageDraw.Draw(img)
            draw.ellipse(
                (self.cx - r, self.cy - r, self.cx + r, self.cy + r),
                fill="white"
            )
            self.disp.ShowImage(img)
            time.sleep(0.02)

        self.disp.clear()


# ----------------------------------------------------------------------
# Standalone test animation
# ----------------------------------------------------------------------

if __name__ == "__main__":
    eye = DroidEye()

    try:
        while True:
            eye.wake_flash()
            eye.listening()
            eye.thinking()
            eye.speaking()
            eye.idle()  # infinite until Ctrl+C

    except KeyboardInterrupt:
        eye.shutdown()

