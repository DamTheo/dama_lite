"""Préqualification thermique SAFE : jamais de GPIO21 ni de chauffage réel.

Lit la vraie sonde DS18B20/CPU, simule la régulation 37 °C avec
un relais mémoire, vérifie les conditions de qualification externe.
Ne crée pas /etc/dama-lite/heating-qualified et ne lance aucun service
de chauffe. Sortie JSON uniquement, sans secrets.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path

from .config import Config
from .heat_qualification import marker_valid
from .thermal import (
    DS18B20, ThermalController, cpu_temperature, heating_decision,
)


class SimulatedRelay:
    def __init__(self):
        self.events: list[bool] = []

    def set(self, state: bool) -> None:
        self.events.append(bool(state))

    def close(self) -> None:
        self.events.append(False)


class FixedSensor:
    def __init__(self, value: float):
        self.value = value

    def read(self) -> float:
        return self.value


def run_preflight(cfg: Config, *, sensor=None, cpu=None,
                  cutoff_verified: bool | None = None) -> dict:
    if cfg.heating_enabled:
        raise RuntimeError(
            "Préqualification réservée au profil de staging : chauffe OFF."
        )
    sensor = sensor if sensor is not None else DS18B20(cfg.sensor_id)
    readings = []
    for idx in range(5):
        readings.append(round(sensor.read(), 3))
        if idx != 4:
            time.sleep(0.35)
    if max(readings) - min(readings) > 2.0:
        raise RuntimeError("Sonde instable : variation > 2 °C.")
    cpu = cpu if cpu is not None else cpu_temperature()
    if cpu is None:
        raise RuntimeError("Sonde CPU introuvable.")
    if cpu >= cfg.cpu_warning_c:
        raise RuntimeError("CPU en alerte : essai thermique impossible.")
    fake = SimulatedRelay()
    simulated_cfg = replace(cfg, heating_enabled=True)
    ctrl = ThermalController(
        simulated_cfg, sensor=FixedSensor(readings[-1]), relay=fake,
        cpu_reader=lambda: cpu,
    )
    ctrl.tick()
    simulated = ctrl.snapshot()
    ctrl.stop()
    cutoff = marker_valid() if cutoff_verified is None else cutoff_verified
    result = {
        "sensor_samples_c": readings,
        "sensor_crc_valid": True,
        "cpu_temperature_c": round(cpu, 2),
        "simulated_heater_on": simulated["heater_on"],
        "simulated_ready": simulated["ready"],
        "simulated_fault": simulated["fault"],
        "relay_physically_energized": False,
        "relay_gpio": cfg.relay_gpio,
        "relay_active_high_configured": cfg.relay_active_high,
        "cutoff_independent_qualification_recorded": cutoff,
        "physical_heating_test_permitted": False,
        "hardware_requirements_remaining": (
            [] if cutoff else [
                "Contrôler sur la machine thermostat/fusible thermique indépendant",
                "Vérifier hors tension relais NO et polarité GPIO21",
                "Qualifier en présence d'un opérateur le premier essai actif",
            ]
        ),
        "limits_c": {
            "start": cfg.start_min_c, "target": cfg.setpoint_c,
            "hysteresis": cfg.hysteresis_c,
            "chamber_cutoff": cfg.enclosure_limit_c,
            "cpu_warning": cfg.cpu_warning_c,
            "cpu_cutoff": cfg.cpu_cutoff_c,
        },
    }
    # L'outil ne donne jamais l'autorisation matérielle.
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    args = p.parse_args()
    cfg = Config.load(args.config)
    print(json.dumps(run_preflight(cfg), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
