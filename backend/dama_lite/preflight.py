"""Diagnostic matériel STRICTEMENT EN LECTURE SEULE pour Incub-resa.

Exécution : PYTHONPATH=backend python3 -m dama_lite.preflight
Option : --config /etc/dama-lite/config.json (lecture sans secrets).
Aucun import de board/digitalio/neopixel/gpiozero ni ouverture des caméras.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .config import Config, ConfigError
from .interlocks import legacy_gpio_processes
from .thermal import DS18B20, SensorError, cpu_temperature


def _text(path: Path, limit: int = 2000) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit].strip()
    except OSError:
        return None


def _command(*args: str, seconds: int = 3) -> str | None:
    try:
        result = subprocess.run(
            list(args), capture_output=True, text=True,
            check=False, timeout=seconds,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def report(config_path: str | None = None) -> dict:
    """Construire un état observable, sans lecture de clés ni commande GPIO."""
    result = {
        "read_only": True,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": platform.node(),
        "model": (_text(Path("/proc/device-tree/model")) or "").strip("\0"),
        "os_release": _text(Path("/etc/os-release"), 1000),
        "cpu_temperature_c": cpu_temperature(),
        "sensor_gpio_overlay": None,
        "enclosure_temperature_c": None,
        "enclosure_sensor_error": None,
        "usb_camera_index0_paths": [],
        "video_devices": [],
        "display_modes": [],
        "backlight_interfaces": [],
        "legacy_gpio_processes": legacy_gpio_processes(),
        "services": {},
        "gpio21_read_only": None,
        "gpio12_read_only": None,
        "sync_clock_state": None,
        "state_disk_free_bytes": None,
        "config": None,
        "pending_hardware_checks": [
            "Polarité du relais GPIO21 et état sans alimentation",
            "Protection thermique indépendante de la commande Raspberry Pi",
            "GPIO et câblage du bouton réel d'extinction",
            "Homogénéité thermique de chacune des huit positions",
            "Identification et alimentation des huit caméras USB",
            "Permissions Graph et certificat applicatif hors Git",
        ],
    }
    cfg_lines = _text(Path("/boot/firmware/config.txt"), 30000) or ""
    result["sensor_gpio_overlay"] = any(
        line.strip() == "dtoverlay=w1-gpio,gpiopin=22"
        for line in cfg_lines.splitlines()
    )
    try:
        result["enclosure_temperature_c"] = DS18B20("28-0000006ca681").read()
    except SensorError as exc:
        result["enclosure_sensor_error"] = str(exc)

    for path in (Path("/dev/v4l/by-path"), Path("/dev/v4l/by-id")):
        if path.is_dir():
            for link in sorted(path.iterdir()):
                if link.name.endswith("video-index0") and link.is_symlink():
                    result["usb_camera_index0_paths"].append({
                        "path": str(link), "target": str(link.resolve())
                    })
    result["video_devices"] = sorted(
        str(p) for p in Path("/dev").glob("video[0-9]*")
    )
    backlight = Path("/sys/class/backlight")
    if backlight.is_dir():
        result["backlight_interfaces"] = sorted(p.name for p in backlight.iterdir())
    modes = Path("/sys/class/drm")
    if modes.is_dir():
        for path in modes.glob("*/modes"):
            value = _text(path, 600)
            if value:
                result["display_modes"].append({"connector": path.parent.name,
                                                "modes": value.splitlines()[:8]})
    for service in ("ssh", "lightdm", "systemd-timesyncd",
                    "dama-lite", "pigpiod"):
        result["services"][service] = _command("systemctl", "is-active", service)
    result["sync_clock_state"] = _command(
        "timedatectl", "show", "-p", "NTPSynchronized", "--value"
    )
    for pin in (12, 21):
        # gpioinfo / pinctrl / raspi-gpio get = lectures d'états seulement ;
        # ne jamais appeler de commande set/mode/export.
        status = _command("pinctrl", "get", str(pin))
        if status is None:
            status = _command("raspi-gpio", "get", str(pin))
        result[f"gpio{pin}_read_only"] = status
    try:
        result["state_disk_free_bytes"] = shutil.disk_usage("/home").free
    except OSError:
        pass
    if config_path is not None:
        try:
            cfg = Config.load(config_path)
            result["config"] = {
                "valid": True,
                "heating_enabled": cfg.heating_enabled,
                "leds_enabled": cfg.leds_enabled,
                "allow_os_shutdown": cfg.allow_os_shutdown,
                "shutdown_button_configured": cfg.shutdown_button_gpio is not None,
                "sharepoint_credentials_configured": cfg.sharepoint.configured,
                "camera_connected": [
                    {"slot": c.slot, "configured": bool(c.device),
                     "exists": bool(c.device and Path(c.device).exists())}
                    for c in cfg.cameras
                ],
            }
        except (OSError, ValueError, TypeError, ConfigError) as exc:
            result["config"] = {"valid": False, "error_type": type(exc).__name__}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit Incub-resa sans écrire sur les GPIO ni caméras"
    )
    parser.add_argument("--config", help="Configuration locale optionnelle (lecture seule)")
    args = parser.parse_args()
    print(json.dumps(report(args.config), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
