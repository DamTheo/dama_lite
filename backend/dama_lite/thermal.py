"""Régulation à hystérésis ; tout défaut de sonde coupe et verrouille le relais.

Le relais physique doit être câblé en position hors tension = chauffe coupée et
protégé par un thermostat/fusible thermique INDEPENDANT du Raspberry Pi.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .config import Config

LOG = logging.getLogger(__name__)


class SensorError(RuntimeError):
    pass


class DS18B20:
    def __init__(self, sensor_id: str):
        self.path = Path("/sys/bus/w1/devices") / sensor_id / "w1_slave"

    def read(self) -> float:
        # Le driver Linux 1-Wire renvoie parfois un CRC NO pendant une
        # conversion; ne pas condamner la machine pour un seul échantillon.
        # Après trois lectures réellement invalides (~0,5 s), on remonte
        # SensorError : ThermalController coupe et verrouille le relais.
        last_error: SensorError | None = None
        for attempt in range(3):
            try:
                lines = self.path.read_text(encoding="ascii").splitlines()
                if len(lines) < 2 or not lines[0].strip().endswith("YES"):
                    raise SensorError("CRC DS18B20 invalide")
                if "t=" not in lines[1]:
                    raise SensorError("Champ température DS18B20 absent")
                temp = float(lines[1].split("t=", 1)[1]) / 1000.0
                # 85 °C peut être une valeur de démarrage, jamais valide.
                if not -20 < temp < 85:
                    raise SensorError(f"Valeur DS18B20 impossible : {temp} °C")
                return temp
            except SensorError as exc:
                last_error = exc
            except (OSError, ValueError, IndexError) as exc:
                last_error = SensorError(f"Lecture DS18B20 impossible : {exc}")
            if attempt < 2:
                time.sleep(0.25)
        raise last_error or SensorError("Sonde DS18B20 sans mesure valide.")


def cpu_temperature() -> float | None:
    try:
        temp = float(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip())
        return round(temp / 1000.0, 3)
    except (OSError, ValueError):
        return None


def heating_decision(was_on: bool, temp: float, target: float, band: float) -> bool:
    """Hystérésis : ON <= cible - marge ; OFF >= cible + marge."""
    if was_on:
        return temp < target + band
    return temp <= target - band


class NullRelay:
    def set(self, enabled: bool) -> None:
        if enabled:
            raise RuntimeError("La chauffe n'est pas autorisée dans ce profil.")

    def close(self) -> None:
        pass


class GPIORelay:
    def __init__(self, bcm_pin: int, active_high: bool):
        import board
        import digitalio

        self._active_high = active_high
        self._output = digitalio.DigitalInOut(getattr(board, f"D{bcm_pin}"))
        # Initialisation directe à l'état INACTIF pour éviter un pulse au démarrage.
        self._output.switch_to_output(value=not active_high)

    def set(self, enabled: bool) -> None:
        self._output.value = bool(enabled) if self._active_high else not bool(enabled)

    def close(self) -> None:
        try:
            self.set(False)
        finally:
            self._output.deinit()


@dataclass
class ThermalSnapshot:
    temperature_c: float | None = None
    cpu_temperature_c: float | None = None
    heater_on: bool = False
    heating_enabled: bool = False
    ready: bool = False
    fault: str | None = None
    cpu_warning: bool = False
    last_read_at: float | None = None


class ThermalController:
    def __init__(
        self,
        cfg: Config,
        sensor=None,
        relay=None,
        cpu_reader: Callable[[], float | None] = cpu_temperature,
    ):
        self.cfg = cfg
        self.sensor = sensor if sensor is not None else DS18B20(cfg.sensor_id)
        self.relay = relay if relay is not None else (
            GPIORelay(cfg.relay_gpio, cfg.relay_active_high)
            if cfg.heating_enabled else NullRelay()
        )
        self.cpu_reader = cpu_reader
        self._state = ThermalSnapshot(heating_enabled=cfg.heating_enabled)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._closed = False

    def tick(self) -> None:
        """Une seule décision de régulation ; aussi testable sans Raspberry Pi."""
        with self._lock:
            if self._stop.is_set():
                self._disable_relay()
                return
            try:
                cpu = self.cpu_reader()
            except Exception:
                cpu = None
            self._state.cpu_temperature_c = cpu
            self._state.cpu_warning = cpu is not None and cpu >= self.cfg.cpu_warning_c
            # Si la télémétrie CPU disparaît, aucune chauffe ne doit
            # rester autorisée : impossible de garantir le seuil d'arrêt.
            if cpu is None and self.cfg.heating_enabled:
                self._state.fault = "SONDE_CPU_INDISPONIBLE"
            try:
                temp = self.sensor.read()
                self._state.temperature_c = round(temp, 3)
                self._state.last_read_at = time.time()
                if temp >= self.cfg.enclosure_limit_c:
                    self._state.fault = "SURCHAUFFE_ENCEINTE"
                if cpu is not None and cpu >= self.cfg.cpu_cutoff_c:
                    self._state.fault = "SURCHAUFFE_RASPBERRY"
                self._state.ready = bool(
                    self.cfg.heating_enabled
                    and self._state.fault is None
                    and temp >= self.cfg.start_min_c
                )
                should_heat = bool(
                    self.cfg.heating_enabled
                    and self._state.fault is None
                    and heating_decision(
                        self._state.heater_on, temp,
                        self.cfg.setpoint_c, self.cfg.hysteresis_c
                    )
                )
                self.relay.set(should_heat)
                self._state.heater_on = should_heat
            except Exception as exc:
                self._state.fault = self._state.fault or f"SONDE_OU_RELAIS: {exc}"
                self._state.ready = False
                self._disable_relay()
                LOG.exception("Défaut thermique verrouillé : %s", exc)
            if self._state.fault:
                self._disable_relay()

    def _disable_relay(self) -> None:
        try:
            self.relay.set(False)
        except Exception:
            LOG.exception("ÉCHEC COUPURE RELAIS : vérifier la sécurité thermique externe !")
        self._state.heater_on = False
        self._state.ready = False

    def snapshot(self) -> dict:
        with self._lock:
            return asdict(self._state)

    def start(self) -> None:
        self.tick()
        self._thread = threading.Thread(target=self._loop, name="thermal", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self.cfg.temperature_poll_s):
            self.tick()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._closed:
                return
            self._disable_relay()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=self.cfg.temperature_poll_s + 2)
        with self._lock:
            if not self._closed:
                try:
                    self.relay.close()
                finally:
                    self._closed = True
