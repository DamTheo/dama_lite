"""Vérification avant *chaque* démarrage du service systemd de staging.

Bloque explicitement si une configuration locale active la chauffe, les LED,
un bouton ou l'arrêt OS. Une modification du JSON ne peut pas activer les
actionneurs via le service de validation au prochain reboot.
"""
from __future__ import annotations

import sys
import stat
from pathlib import Path

from .config import Config

STAGING_CONFIG = Path("/home/damocles/dama-lite-staging/config.staging.json")
SHUTDOWN_AUTHORIZATION = Path("/etc/dama-lite/shutdown-ui-authorized")
SHUTDOWN_AUTH_VALUE = "DAMA_LITE_UI_POWER_OFF_AUTHORIZED"


def shutdown_approved(marker: Path = SHUTDOWN_AUTHORIZATION) -> bool:
    if marker.is_symlink() or not marker.is_file():
        return False
    meta = marker.stat()
    return (
        meta.st_uid == 0
        and stat.S_IMODE(meta.st_mode) & 0o022 == 0
        and marker.read_text(encoding="ascii").strip() == SHUTDOWN_AUTH_VALUE
    )


def validate_staging(cfg: Config) -> None:
    unsafe = []
    if cfg.heating_enabled:
        unsafe.append("chauffage")
    if cfg.leds_enabled:
        unsafe.append("LED")
    if cfg.allow_os_shutdown and not shutdown_approved():
        unsafe.append("extinction OS sans autorisation opérateur")
    if cfg.shutdown_button_gpio is not None:
        unsafe.append("bouton GPIO")
    if unsafe:
        raise RuntimeError(
            "Service STAGING interdit d'actionner : " + ", ".join(unsafe)
        )


def main() -> None:
    config = Config.load(STAGING_CONFIG)
    validate_staging(config)
    print(
        "DAMA Lite STAGING : chauffage et LED internes désactivés ; "
        "extinction OS autorisée=" + str(config.allow_os_shutdown)
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Pré-démarrage staging refusé : {exc}", file=sys.stderr)
        raise SystemExit(1)
