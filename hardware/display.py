#!/usr/bin/env python3
"""
StreamStation Hardware Display Driver
Reads current_channel.json and updates physical display hardware.
Supports: TM1637 7-segment, I2C LCD (16x2 / 20x4)
"""

import os
import sys
import json
import time
import logging
import argparse
import threading
from pathlib import Path

BASE_DIR    = Path(__file__).parent.parent
STATUS_FILE = BASE_DIR / "runtime" / "current_channel.json"
CONFIG_FILE = BASE_DIR / "config" / "system.json"

log = logging.getLogger("streamstation.display")


def load_json(path):
    with open(path) as f:
        return json.load(f)


# ── TM1637 Driver ────────────────────────────────────────────────────────────
class TM1637Display:
    """4-digit 7-segment display via TM1637 chip (common Pi cable box mod)."""

    def __init__(self, clk_pin, dio_pin, brightness=3):
        try:
            import tm1637
            self.display = tm1637.TM1637(clk=clk_pin, dio=dio_pin)
            self.display.brightness(brightness)
            self.available = True
            log.info(f"TM1637 initialized on CLK={clk_pin}, DIO={dio_pin}")
        except ImportError:
            log.warning("tm1637 library not found — install with: pip install tm1637")
            self.available = False
        except Exception as e:
            log.warning(f"TM1637 init failed: {e}")
            self.available = False

    def show_channel(self, number):
        if not self.available:
            return
        try:
            self.display.number(number)
        except Exception as e:
            log.warning(f"TM1637 show error: {e}")

    def show_dashes(self):
        if not self.available:
            return
        try:
            self.display.write([0x40, 0x40, 0x40, 0x40])  # four dashes
        except Exception as e:
            log.warning(f"TM1637 dash error: {e}")

    def show_text(self, text):
        """Show up to 4 chars."""
        if not self.available:
            return
        try:
            self.display.show(text[:4].upper())
        except Exception as e:
            log.warning(f"TM1637 text error: {e}")


# ── I2C LCD Driver ────────────────────────────────────────────────────────────
class LCDDisplay:
    """I2C character LCD (16x2 or 20x4) via RPLCD library."""

    def __init__(self, i2c_address=0x27, cols=16, rows=2):
        try:
            from RPLCD.i2c import CharLCD
            self.lcd = CharLCD(
                i2c_expander='PCF8574',
                address=i2c_address,
                port=1,
                cols=cols,
                rows=rows,
                dotsize=8
            )
            self.cols = cols
            self.rows = rows
            self.available = True
            self.lcd.clear()
            log.info(f"LCD initialized at I2C 0x{i2c_address:02X}, {cols}x{rows}")
        except ImportError:
            log.warning("RPLCD not found — install with: pip install RPLCD")
            self.available = False
        except Exception as e:
            log.warning(f"LCD init failed: {e}")
            self.available = False

    def show_channel(self, number, name=""):
        if not self.available:
            return
        try:
            self.lcd.clear()
            self.lcd.cursor_pos = (0, 0)
            ch_str = f"CH {number:>4}"
            self.lcd.write_string(ch_str.ljust(self.cols))
            if self.rows >= 2 and name:
                self.lcd.cursor_pos = (1, 0)
                self.lcd.write_string(name[:self.cols].ljust(self.cols))
        except Exception as e:
            log.warning(f"LCD show_channel error: {e}")

    def show_text(self, line1="", line2=""):
        if not self.available:
            return
        try:
            self.lcd.clear()
            self.lcd.cursor_pos = (0, 0)
            self.lcd.write_string(line1[:self.cols].ljust(self.cols))
            if self.rows >= 2:
                self.lcd.cursor_pos = (1, 0)
                self.lcd.write_string(line2[:self.cols].ljust(self.cols))
        except Exception as e:
            log.warning(f"LCD show_text error: {e}")

    def scroll_name(self, number, name):
        """Scroll a long channel name across the bottom row."""
        if not self.available or len(name) <= self.cols:
            self.show_channel(number, name)
            return
        padded = name + "  "
        self.lcd.cursor_pos = (0, 0)
        self.lcd.write_string(f"CH {number:>4}".ljust(self.cols))
        for i in range(len(padded) - self.cols + 1):
            try:
                self.lcd.cursor_pos = (1, 0)
                self.lcd.write_string(padded[i:i+self.cols])
                time.sleep(0.3)
            except Exception:
                break


# ── Display Manager ────────────────────────────────────────────────────────────
class DisplayManager:
    def __init__(self, config):
        hw = config.get("hardware", {})
        display_type = hw.get("display_type", "tm1637")

        self.seg    = None
        self.lcd    = None
        self._last  = None

        if display_type in ("tm1637", "both"):
            clk = hw.get("tm1637_clk", 23)
            dio = hw.get("tm1637_dio", 24)
            bri = hw.get("tm1637_brightness", 3)
            self.seg = TM1637Display(clk, dio, bri)

        if display_type in ("lcd", "both"):
            addr = hw.get("lcd_address", 0x27)
            cols = hw.get("lcd_cols", 16)
            rows = hw.get("lcd_rows", 2)
            self.lcd = LCDDisplay(addr, cols, rows)

    def update(self, channel, name, state):
        key = (channel, state)
        if key == self._last:
            return
        self._last = key

        if channel and state == "playing":
            if self.seg:
                self.seg.show_channel(channel)
            if self.lcd:
                self.lcd.show_channel(channel, name or "")
            log.info(f"Display: CH {channel} — {name}")
        else:
            if self.seg:
                self.seg.show_dashes()
            if self.lcd:
                self.lcd.show_text("STREAMSTATION", "NO SIGNAL")

    def run(self, poll_interval=1.0):
        log.info("Display driver running — polling status file")
        while True:
            try:
                status = load_json(STATUS_FILE)
                self.update(
                    status.get("channel"),
                    status.get("name", ""),
                    status.get("state", "idle"),
                )
            except Exception as e:
                log.debug(f"Status read error: {e}")
            time.sleep(poll_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="StreamStation Display Driver")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        cfg = load_json(CONFIG_FILE)
    except Exception:
        cfg = {}
    mgr = DisplayManager(cfg)
    mgr.run()
