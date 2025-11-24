#!/usr/bin/python3
# -*- coding:utf-8 -*-

import time
import math
import os
import sys
from PIL import Image, ImageDraw

# Path to Waveshare LCD driver
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

        # Backlight ON
        try:
            if hasattr(self.disp, "bl_DutyCycle"):
                self.disp.bl_DutyCycle(100)
            elif hasattr(self.disp, "BL_DutyCycle"):
                self.disp.BL_DutyCycle(100)
        except Exception as e:
            print("[eye] Could not set backlight:", e)

        self.width = self.disp.width
        self.height = self.disp.height
        self.cx = self.width // 2
        self.cy = self.height // 2
        self.radius = min(self.width, self.height) // 3

        self.running = True
        
    # -------------------------------------------------------------
    # DRAW THE EYE
    # -------------------------------------------------------------
    def _draw_eye(self, x_offset=0, y_offset=0, brightness=255):
        """Draw a single fuzzy glowing orb that can move around."""

        brightness = max(0, min(255, int(brightness)))

        # Base image
        img = Image.new("RGB", (self.width, self.height), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Orb position
        max_off = self.radius
        ox = self.cx + max(-max_off, min(max_off, x_offset))
        oy = self.cy + max(-max_off, min(max_off, y_offset))

        # Orb radius
        r = self.radius

        # We’ll draw a fuzzy glow manually with concentric alpha layers
        layers = 8
        for i in range(layers):
            # The farther out the circle, the dimmer it is
            factor = (layers - i) / layers
            alpha = int(brightness * factor * 0.5)   # outer layers are softer

            rr = int(r * factor)

            # Convert alpha to a gray level since the panel isn't alpha-capable
            gray = alpha

            draw.ellipse(
                (ox - rr, oy - rr, ox + rr, oy + rr),
                fill=(gray, gray, gray)
            )

        self.disp.ShowImage(img)
    # -------------------------------------------------------------
    # STATE HELPERS
    # -------------------------------------------------------------
    def idle(self):
        """Dim, centered glow (waiting for wake word)."""
        self._draw_eye(brightness=90)

    def wake_flash(self):
        """Quick bright flash when wake word is detected."""
        for _ in range(2):
            self._draw_eye(brightness=255)
            time.sleep(0.08)
            self._draw_eye(brightness=130)
            time.sleep(0.08)

    def listening(self):
        """Slightly brighter, attentive glow while listening."""
        self._draw_eye(brightness=200)

    def thinking(self, cycles: int = 6):
        """Short pulse effect while generating a reply."""
        t = 0.0
        for _ in range(cycles):
            b = int(160 + 70 * math.sin(t))
            self._draw_eye(brightness=b)
            t += 0.6
            time.sleep(0.05)

    def speaking(self):
        """Steady, confident glow while TTS is playing."""
        self._draw_eye(brightness=190)

    def standby(self):
        """Dimmer glow when going back to sleep / standby."""
        self._draw_eye(brightness=30)


    # -------------------------------------------------------------
    # QUICK TEST ANIMATION
    # -------------------------------------------------------------
    def test(self):
        """Simple animation to confirm LCD drawing works."""
        print("[eye-test] Static bright eye")
        self._draw_eye(brightness=220)
        time.sleep(2)

        print("[eye-test] Moving pupil")
        for off in [-40, 0, 40, 0]:
            self._draw_eye(x_offset=off, brightness=220)
            time.sleep(0.4)

        print("[eye-test] Breathing brightness")
        t = 0
        for _ in range(40):
            b = int(150 + 80 * math.sin(t))
            self._draw_eye(brightness=b)
            t += 0.2
            time.sleep(0.05)

    # -------------------------------------------------------------
    def shutdown(self):
        """Fade the eye out."""
        for r in range(self.radius, 0, -4):
            img = Image.new("RGB", (self.width, self.height), "black")
            draw = ImageDraw.Draw(img)
            draw.ellipse(
                (self.cx - r, self.cy - r,
                 self.cx + r, self.cy + r),
                fill="white"
            )
            self.disp.ShowImage(img)
            time.sleep(0.02)

        self.disp.clear()


# -------------------------------------------------------------
# MAIN (TEST MODE)
# -------------------------------------------------------------
if __name__ == "__main__":
    eye = DroidEye()
    try:
        eye.test()
    except KeyboardInterrupt:
        pass
    finally:
        eye.shutdown()
