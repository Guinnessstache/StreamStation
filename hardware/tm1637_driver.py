#!/usr/bin/env python3
"""
TM1637 4-digit 7-segment display driver.
Pure RPi.GPIO implementation — no external library needed.
Tested on Raspberry Pi 5.
"""

import time
import RPi.GPIO as GPIO

SEGMENTS = {
    0: 0x3f, 1: 0x06, 2: 0x5b, 3: 0x4f,
    4: 0x66, 5: 0x6d, 6: 0x7d, 7: 0x07,
    8: 0x7f, 9: 0x6f, '-': 0x40, ' ': 0x00,
    'A': 0x77, 'b': 0x7c, 'C': 0x39, 'd': 0x5e,
    'E': 0x79, 'F': 0x71, 'H': 0x76, 'L': 0x38,
    'n': 0x54, 'o': 0x5c, 'P': 0x73, 'r': 0x50,
    'S': 0x6d, 't': 0x78, 'U': 0x3e, 'y': 0x6e,
}


class TM1637:
    def __init__(self, clk, dio, brightness=3):
        self.clk = clk
        self.dio = dio
        self.brightness = min(7, max(0, brightness))
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.clk, GPIO.OUT)
        GPIO.setup(self.dio, GPIO.OUT)
        GPIO.output(self.clk, GPIO.HIGH)
        GPIO.output(self.dio, GPIO.HIGH)

    def _start(self):
        GPIO.output(self.dio, GPIO.HIGH)
        GPIO.output(self.clk, GPIO.HIGH)
        time.sleep(0.0001)
        GPIO.output(self.dio, GPIO.LOW)
        time.sleep(0.0001)
        GPIO.output(self.clk, GPIO.LOW)

    def _stop(self):
        GPIO.output(self.clk, GPIO.LOW)
        GPIO.output(self.dio, GPIO.LOW)
        time.sleep(0.0001)
        GPIO.output(self.clk, GPIO.HIGH)
        time.sleep(0.0001)
        GPIO.output(self.dio, GPIO.HIGH)

    def _write_byte(self, data):
        for _ in range(8):
            GPIO.output(self.clk, GPIO.LOW)
            GPIO.output(self.dio, GPIO.HIGH if (data & 1) else GPIO.LOW)
            data >>= 1
            time.sleep(0.0001)
            GPIO.output(self.clk, GPIO.HIGH)
            time.sleep(0.0001)
        # ACK cycle
        GPIO.output(self.clk, GPIO.LOW)
        GPIO.output(self.dio, GPIO.HIGH)
        GPIO.setup(self.dio, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        time.sleep(0.0001)
        GPIO.output(self.clk, GPIO.HIGH)
        time.sleep(0.0001)
        GPIO.output(self.clk, GPIO.LOW)
        GPIO.setup(self.dio, GPIO.OUT)

    def show(self, digits):
        """Show up to 4 digits. Each element should be a key in SEGMENTS."""
        # Pad or truncate to 4
        padded = (list(digits) + [' ', ' ', ' ', ' '])[:4]
        self._start()
        self._write_byte(0x40)  # auto-increment address mode
        self._stop()
        self._start()
        self._write_byte(0xC0)  # start at address 0
        for d in padded:
            self._write_byte(SEGMENTS.get(d, 0x00))
        self._stop()
        self._start()
        self._write_byte(0x88 | self.brightness)  # display on + brightness
        self._stop()

    def number(self, n):
        """Display an integer 0–9999, blanking leading zeros."""
        n = max(0, min(9999, n))
        d = [n // 1000, (n // 100) % 10, (n // 10) % 10, n % 10]
        # Blank leading zeros (keep at least the last digit)
        for i in range(3):
            if d[i] == 0 and all(x == 0 for x in d[:i+1]):
                d[i] = ' '
        self.show(d)

    def dashes(self):
        """Show ---- (no signal / idle)."""
        self.show(['-', '-', '-', '-'])

    def off(self):
        """Turn display off."""
        self._start()
        self._write_byte(0x80)  # display off
        self._stop()

    def cleanup(self):
        self.off()
        GPIO.cleanup()
