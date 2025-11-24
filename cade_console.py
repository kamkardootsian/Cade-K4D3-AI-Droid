#!/usr/bin/env python3
import subprocess
import sys
import shutil
import time

# Simple ANSI helpers
RESET = "\033[0m"
GREEN = "\033[32m"
DIM = "\033[2m"
BOLD = "\033[1m"
CLEAR = "\033[2J\033[H"  # clear screen + home cursor

SERVICE_NAME = "cade.service"


def draw_header():
    cols = shutil.get_terminal_size((80, 20)).columns
    title = " K4D3 // DIAGNOSTIC CONSOLE "
    border = "=" * cols
    padded = title.center(cols)

    print(CLEAR, end="")
    print(GREEN + border + RESET)
    print(GREEN + padded + RESET)
    print(GREEN + border + RESET)
    print(DIM + "Source: journalctl --user -fu cade.service" + RESET)
    print()


def style_line(line: str) -> str:
    """Apply simple 'Star Wars terminal' styling based on content."""
    line = line.rstrip("\n")

    # Highlight Cade state tags if present
    if "[STATE]" in line:
        return BOLD + GREEN + line + RESET
    if "[IDLE]" in line or "[ACTIVE]" in line or "[wake]" in line:
        return GREEN + line + RESET
    if "ERROR" in line or "Failed" in line:
        # red-ish, but we can keep it greenish by mixing; for now just dim
        return BOLD + line + RESET

    # Default: dim green
    return DIM + GREEN + line + RESET


def main():
    draw_header()
    time.sleep(0.3)

    # Start journalctl follow for this user service
    cmd = ["journalctl", "--user-unit=cade.service", "-f"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        print("journalctl not found. Are you on systemd?")
        sys.exit(1)

    try:
        for raw_line in proc.stdout:
            # On first run, journalctl prints some history; you can keep or trim.
            styled = style_line(raw_line)
            print(styled)
    except KeyboardInterrupt:
        print("\n" + DIM + "Closing K4D3 console..." + RESET)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
