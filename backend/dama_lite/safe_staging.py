"""Vérification avant *chaque* démarrage du service systemd de staging.

Bloque explicitement si une configuration locale active la chauffe, les LED,
un bouton ou l'arrêt OS. Une modification du JSON ne peut pas activer les
actionneurs via le service de validation au prochain reboot.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .config import Config

STAGING_CONFIG = Path("/home/damocles/dama-lite-staging/config.staging.json")


def validate_staging(cfg: Config) -> None:
    unsafe = []
    if cfg.heating_enabled:
        unsafe.append("chauffage")
    if cfg.leds_enabled:
        unsafe.append("LED")
    if cfg.allow_os_shutdown:
        unsafe.append("arrêt du système")
    if cfg.shutdown_button_gpio is not None:
        unsafe.append("bouton GPIO")
    if unsafe:
        raise RuntimeError(
            "Service STAGING interdit d'actionner : " + ", ".join(unsafe)
        )


def main() -> None:
    config = Config.load(STAGING_CONFIG)
    validate_staging(config)
    print("DAMA Lite STAGING : chauffage, LED et extinction désactivés.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Pré-démarrage staging refusé : {exc}", file=sys.stderr)
        raise SystemExit(1)
