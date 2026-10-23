"""64 NeoPixels adressés en 8 groupes de 8, sans interférence avec les photos."""
from __future__ import annotations

import logging
import threading

LOG = logging.getLogger(__name__)

COLOR = {
    "available": (0, 255, 0),
    "running": (255, 170, 0),
    "fault": (255, 0, 0),
    "off": (0, 0, 0),
}


def pixel_colors(states: list[str]) -> list[tuple[int, int, int]]:
    if len(states) != 8 or any(state not in COLOR for state in states):
        raise ValueError("Il faut exactement 8 états LED valides.")
    return [COLOR[state] for state in states for _ in range(8)]


class LightController:
    def __init__(self, enabled: bool, gpio: int, brightness: float, driver=None):
        self._lock = threading.RLock()
        self._blackout_depth = 0
        self._last = None
        self.driver = driver
        if enabled and driver is None:
            import board
            import neopixel
            self.driver = neopixel.NeoPixel(
                getattr(board, f"D{gpio}"), 64,
                brightness=brightness, auto_write=False,
            )
        if self.driver is not None:
            self._write([(0, 0, 0)] * 64)

    def _write(self, colors: list[tuple[int, int, int]]) -> None:
        if self.driver is not None:
            for i, value in enumerate(colors):
                self.driver[i] = value
            self.driver.show()

    def update(self, states: list[str]) -> None:
        with self._lock:
            self._last = pixel_colors(states)
            if self._blackout_depth == 0:
                self._write(self._last)

    def blackout_on(self) -> None:
        with self._lock:
            self._blackout_depth += 1
            self._write([(0, 0, 0)] * 64)

    def blackout_off(self) -> None:
        with self._lock:
            self._blackout_depth = max(0, self._blackout_depth - 1)
            if self._blackout_depth == 0 and self._last is not None:
                self._write(self._last)

    def close(self) -> None:
        with self._lock:
            try:
                self._write([(0, 0, 0)] * 64)
            finally:
                if self.driver is not None and hasattr(self.driver, "deinit"):
                    self.driver.deinit()
