#!/usr/bin/env python3
"""
StreamStation Hardware Keypad Driver
Reads 4x4 matrix keypad and sends channel commands to the engine.
* = Channel Down, # = Channel Up, 0-9 = direct channel entry
"""

import sys
import json
import time
import socket
import logging
import argparse
import threading
from pathlib import Path

BASE_DIR       = Path(__file__).parent.parent
CONFIG_FILE    = BASE_DIR / "config" / "system.json"
CONTROL_SOCKET = BASE_DIR / "runtime" / "control.socket"

log = logging.getLogger("streamstation.keypad")

# Standard 4x4 matrix keypad layout
KEYMAP = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D'],
]

# Default GPIO pins (BCM numbering) — rows then cols
DEFAULT_ROWS = [5, 6, 13, 19]
DEFAULT_COLS = [12, 16, 20, 21]

ENTRY_TIMEOUT = 2.5  # seconds


def send_command(cmd):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(3)
            s.connect(str(CONTROL_SOCKET))
            s.sendall((cmd + "\n").encode())
            return s.recv(256).decode().strip()
    except Exception as e:
        log.warning(f"Socket error: {e}")
        return None


class KeypadDriver:
    def __init__(self, row_pins, col_pins):
        self.row_pins    = row_pins
        self.col_pins    = col_pins
        self.entry_buf   = ""
        self.entry_timer = None
        self._gpio_ok    = False
        self._init_gpio()

    def _init_gpio(self):
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for pin in self.row_pins:
                GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
            for pin in self.col_pins:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self._gpio_ok = True
            log.info(f"GPIO initialized: rows={self.row_pins}, cols={self.col_pins}")
        except ImportError:
            log.warning("RPi.GPIO not found — keypad unavailable (not on Pi?)")
        except Exception as e:
            log.warning(f"GPIO init failed: {e}")

    def scan(self):
        """Return pressed key char or None."""
        if not self._gpio_ok:
            return None
        GPIO = self.GPIO
        for r_idx, row_pin in enumerate(self.row_pins):
            GPIO.output(row_pin, GPIO.LOW)
            for c_idx, col_pin in enumerate(self.col_pins):
                if GPIO.input(col_pin) == GPIO.LOW:
                    GPIO.output(row_pin, GPIO.HIGH)
                    return KEYMAP[r_idx][c_idx]
            GPIO.output(row_pin, GPIO.HIGH)
        return None

    def handle_key(self, key):
        if key is None:
            return
        log.debug(f"Key pressed: {key}")

        if key == '*':
            self._clear_entry()
            send_command("DOWN")
        elif key == '#':
            self._clear_entry()
            send_command("UP")
        elif key == 'A':
            self._clear_entry()
            send_command("LAST")
        elif key.isdigit():
            self._digit(key)
        # B/C/D reserved for future use

    def _digit(self, d):
        self.entry_buf += d
        log.info(f"Channel entry: {self.entry_buf}")
        if self.entry_timer:
            self.entry_timer.cancel()
        if len(self.entry_buf) >= 3:
            self._commit()
        else:
            self.entry_timer = threading.Timer(ENTRY_TIMEOUT, self._commit)
            self.entry_timer.start()

    def _commit(self):
        num = self.entry_buf
        self.entry_buf = ""
        if self.entry_timer:
            self.entry_timer.cancel()
            self.entry_timer = None
        if num:
            log.info(f"Tuning to CH {num}")
            send_command(f"TUNE {num}")

    def _clear_entry(self):
        self.entry_buf = ""
        if self.entry_timer:
            self.entry_timer.cancel()
            self.entry_timer = None

    def cleanup(self):
        if self._gpio_ok:
            self.GPIO.cleanup()
        log.info("GPIO cleaned up")

    def run(self, poll_hz=20):
        log.info("Keypad driver running")
        interval  = 1.0 / poll_hz
        last_key  = None
        debounce  = 0

        try:
            while True:
                key = self.scan()
                if key and key != last_key and debounce == 0:
                    self.handle_key(key)
                    last_key = key
                    debounce = 3  # ~150ms at 20Hz
                elif not key:
                    last_key = None
                if debounce > 0:
                    debounce -= 1
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StreamStation Keypad Driver")
    parser.add_argument("--rows", nargs=4, type=int, default=DEFAULT_ROWS, metavar="PIN",
                        help="4 GPIO row pins (BCM)")
    parser.add_argument("--cols", nargs=4, type=int, default=DEFAULT_COLS, metavar="PIN",
                        help="4 GPIO col pins (BCM)")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    drv = KeypadDriver(args.rows, args.cols)
    drv.run()
