"""Garde de bascule de production du relais GPIO21.

JAMAIS de commande GPIO dans ce module. Une vérification logicielle
ne saurait remplacer un thermostat/fusible thermique indépendant.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

from .config import Config
from .thermal import DS18B20, cpu_temperature

MARKER = Path("/etc/dama-lite/heating-qualified")
MARKER_TEXT = "CUTOFF_INDEPENDENT_VERIFIED_GPIO21_ACTIVE_HIGH"


class QualificationError(RuntimeError):
    pass


def marker_valid(path: Path = MARKER) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    metadata = path.stat()
    return (
        metadata.st_uid == 0
        and stat.S_IMODE(metadata.st_mode) & 0o077 == 0
        and path.read_text(encoding="ascii").strip() == MARKER_TEXT
    )


def validate_before_heating(
    config: Config, *, marker: Path = MARKER, sensor=None, cpu_reader=cpu_temperature
) -> dict:
    if not config.heating_enabled:
        raise QualificationError("Le profil demandé n'active pas la chauffe.")
    if not marker_valid(marker):
        raise QualificationError(
            "Chauffe interdite : absence de qualification physique indépendante."
        )
    if config.relay_gpio != 21 or not config.relay_active_high:
        raise QualificationError("Polarité du relais différente du matériel audité.")
    therm = sensor if sensor is not None else DS18B20(config.sensor_id)
    values = [therm.read() for _ in range(3)]
    if any(temp >= config.enclosure_limit_c for temp in values):
        raise QualificationError("Température enceinte dépassant la limite.")
    if max(values) - min(values) > 2.0:
        raise QualificationError("Mesures DS18B20 incohérentes.")
    cpu = cpu_reader()
    if cpu is None or cpu >= config.cpu_warning_c:
        raise QualificationError("CPU trop chaud ou capteur CPU indisponible.")
    return {
        "cutoff_marker_valid": True,
        "relay_gpio": config.relay_gpio,
        "active_high": config.relay_active_high,
        "sensor_samples_c": [round(t, 2) for t in values],
        "cpu_temperature_c": round(cpu, 2),
        "heating_commanded": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--guard", action="store_true", required=True)
    p.add_argument("--config", required=True)
    args = p.parse_args()
    cfg = Config.load(args.config)
    print(json.dumps(validate_before_heating(cfg), ensure_ascii=False))


if __name__ == "__main__":
    main()
