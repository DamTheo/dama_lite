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
        # Verrouillage également à l'instanciation : ne pas dépendre
        # uniquement de la lecture du fichier JSON.
        if not 0 < brightness <= 0.10:
            raise ValueError("L'intensité des 64 LED ne doit jamais dépasser 10 %.")
        self._lock = threading.RLock()
        self._blackout_depth = 0
        self._last = None
        self._sent = None
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
        values = tuple(colors)
        if self.driver is not None and values != self._sent:
            for i, value in enumerate(values):
                self.driver[i] = value
            self.driver.show()
            self._sent = values

    def update(
        self, states: list[str], *, pulse_slot: int | None = None,
        pulse_factor: float = 1.0,
    ) -> None:
        if not 0.0 <= pulse_factor <= 1.0:
            raise ValueError("Un pulse LED ne peut pas augmenter l'intensité.")
        if pulse_slot is not None and (type(pulse_slot) is not int or not 1 <= pulse_slot <= 8):
            raise ValueError("Groupe LED hors plage 1-8.")
        with self._lock:
            self._last = pixel_colors(states)
            output = list(self._last)
            # Le pulse ne remplace jamais un défaut rouge ni une analyse
            # jaune ; il assombrit seulement la position verte choisie.
            if pulse_slot is not None and states[pulse_slot - 1] == "available":
                offset = (pulse_slot - 1) * 8
                for i in range(offset, offset + 8):
                    output[i] = tuple(int(channel * pulse_factor) for channel in output[i])
            if self._blackout_depth == 0:
                self._write(output)

    @property
    def blackout_active(self) -> bool:
        with self._lock:
            return self._blackout_depth > 0

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
