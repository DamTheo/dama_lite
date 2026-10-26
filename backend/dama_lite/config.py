"""Chargement strict des paramètres matériels. Aucun secret n'est embarqué dans Git."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SHAREPOINT_ROOT = (
    "03_Projets/04_Résazurine/03_Expérimentations & Résultats/DAMA-Lite"
)


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CameraSpec:
    slot: int
    device: str | None
    width: int = 1280
    height: int = 720
    pixel_format: str = "MJPG"

    def __post_init__(self):
        if not 1 <= self.slot <= 8:
            raise ConfigError("La caméra doit correspondre à un emplacement 1–8.")
        if self.device and not (
            self.device.startswith("/dev/v4l/by-path/")
            or self.device.startswith("/dev/v4l/by-id/")
        ):
            raise ConfigError("Les caméras exigent un chemin USB persistant /dev/v4l/by-path ou by-id.")
        if not 320 <= self.width <= 4096 or not 240 <= self.height <= 3072:
            raise ConfigError("Résolution caméra non prise en charge.")
        if self.pixel_format not in {"MJPG", "YUYV"}:
            raise ConfigError("Format caméra USB non autorisé (MJPG ou YUYV).")


@dataclass(frozen=True)
class SharePointConfig:
    tenant_id: str = ""
    client_id: str = ""
    drive_id: str = ""
    private_key_path: str = ""
    public_cert_path: str = ""
    client_secret_path: str = ""
    graph_env_path: str = ""
    graph_folder_id: str = ""
    folder_root: str = SHAREPOINT_ROOT
    expected_drive_name: str = "R&D Biologie"

    @property
    def configured(self) -> bool:
        common = all([self.tenant_id, self.client_id, self.drive_id])
        certificate = bool(self.private_key_path and self.public_cert_path)
        client_secret = bool(self.client_secret_path)
        return bool(common and (certificate or client_secret or self.graph_env_path))

    def __post_init__(self):
        certificate = bool(self.private_key_path or self.public_cert_path)
        if self.graph_env_path and (certificate or self.client_secret_path):
            raise ConfigError("Entra : fichier existant OU certificat/secret séparé.")
        if self.graph_env_path and not Path(self.graph_env_path).is_absolute():
            raise ConfigError("Le fichier Entra exige un chemin absolu.")
        if self.client_secret_path and certificate:
            raise ConfigError(
                "Entra : choisir certificat OU secret client, jamais les deux."
            )
        if bool(self.private_key_path) != bool(self.public_cert_path):
            raise ConfigError("Le certificat public exige une clé privée associée.")
        if self.client_secret_path and not Path(self.client_secret_path).is_absolute():
            raise ConfigError("Le secret Entra doit être un fichier à chemin absolu.")
        if self.folder_root.strip("/") != SHAREPOINT_ROOT:
            raise ConfigError(
                "La destination doit être DAMA-Lite directement, sans sous-dossier caméra/date."
            )
        if self.expected_drive_name != "R&D Biologie":
            raise ConfigError(
                "La bibliothèque SharePoint doit être explicitement R&D Biologie."
            )


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    state_dir: Path
    ui_dir: Path
    sensor_id: str
    heating_enabled: bool
    relay_gpio: int
    relay_active_high: bool
    setpoint_c: float
    start_min_c: float
    hysteresis_c: float
    enclosure_limit_c: float
    cpu_warning_c: float
    cpu_cutoff_c: float
    temperature_poll_s: float
    leds_enabled: bool
    led_gpio: int
    led_brightness: float
    camera_interval_s: int
    spool_limit_bytes: int
    cameras: tuple[CameraSpec, ...]
    sharepoint: SharePointConfig
    shutdown_button_gpio: int | None
    allow_os_shutdown: bool
    shutdown_animation_s: float

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        # Ne jamais interpréter la chaîne "false" comme True pour activer
        # accidentellement le chauffage ou l'extinction système.
        for flag in ("heating_enabled", "relay_active_high", "leds_enabled",
                     "allow_os_shutdown"):
            if flag in raw and type(raw[flag]) is not bool:
                raise ConfigError(f"{flag} doit être un vrai booléen JSON.")
        default_cameras = [{"slot": n, "device": None} for n in range(1, 9)]
        cameras = tuple(CameraSpec(**entry) for entry in raw.get("cameras", default_cameras))
        if len(cameras) != 8 or {cam.slot for cam in cameras} != set(range(1, 9)):
            raise ConfigError("La configuration doit déclarer exactement 8 emplacements distincts.")
        devices = [c.device for c in cameras if c.device]
        if len(devices) != len(set(devices)):
            raise ConfigError("Deux emplacements ne peuvent pas utiliser le même périphérique USB.")
        sp_raw = dict(raw.get("sharepoint", {}))
        if sp_raw.get("graph_env_path"):
            from .entra_env import read_graph_env

            env_data = read_graph_env(sp_raw["graph_env_path"])
            for prop, key in (
                ("tenant_id", "MS_TENANT_ID"),
                ("client_id", "MS_CLIENT_ID"),
                ("drive_id", "MS_DRIVE_ID"),
            ):
                if sp_raw.get(prop) and sp_raw[prop] != env_data[key]:
                    raise ConfigError(
                        f"Identifiant {prop} incohérent avec le fichier Entra."
                    )
                sp_raw[prop] = env_data[key]
            sp_raw["graph_folder_id"] = env_data.get("MS_FOLDER_ID", "")
        sp = SharePointConfig(**sp_raw)
        c = cls(
            host=raw.get("host", "127.0.0.1"),
            port=int(raw.get("port", 8765)),
            state_dir=Path(raw.get("state_dir", "/var/lib/dama-lite")),
            ui_dir=Path(raw.get("ui_dir", "/opt/dama-lite/ui/dist")),
            sensor_id=raw.get("sensor_id", "28-0000006ca681"),
            heating_enabled=raw.get("heating_enabled", False),
            relay_gpio=int(raw.get("relay_gpio", 21)),
            relay_active_high=raw.get("relay_active_high", True),
            setpoint_c=float(raw.get("setpoint_c", 37.0)),
            start_min_c=float(raw.get("start_min_c", 35.0)),
            hysteresis_c=float(raw.get("hysteresis_c", 0.3)),
            enclosure_limit_c=float(raw.get("enclosure_limit_c", 41.0)),
            cpu_warning_c=float(raw.get("cpu_warning_c", 65.0)),
            cpu_cutoff_c=float(raw.get("cpu_cutoff_c", 80.0)),
            temperature_poll_s=float(raw.get("temperature_poll_s", 2.0)),
            leds_enabled=raw.get("leds_enabled", False),
            led_gpio=int(raw.get("led_gpio", 12)),
            led_brightness=float(raw.get("led_brightness", 0.1)),
            camera_interval_s=int(raw.get("camera_interval_s", 300)),
            spool_limit_bytes=int(raw.get("spool_limit_bytes", 4 * 1024**3)),
            cameras=tuple(sorted(cameras, key=lambda cam: cam.slot)),
            sharepoint=sp,
            shutdown_button_gpio=raw.get("shutdown_button_gpio"),
            allow_os_shutdown=raw.get("allow_os_shutdown", False),
            shutdown_animation_s=float(raw.get("shutdown_animation_s", 4.8)),
        )
        if c.host != "127.0.0.1":
            raise ConfigError("L'API doit rester strictement sur 127.0.0.1.")
        if c.relay_gpio != 21 or c.led_gpio != 12:
            raise ConfigError("Incohérence avec les GPIO matériels confirmés (relais 21, LED 12).")
        if c.sensor_id != "28-0000006ca681":
            raise ConfigError("Identifiant DS18B20 inconnu : vérifier physiquement avant activation.")
        if not 0 < c.port < 65536:
            raise ConfigError("Port HTTP invalide.")
        if not 0 < c.hysteresis_c < 1.5:
            raise ConfigError("Hystérésis invalide.")
        if c.setpoint_c != 37 or c.start_min_c != 35:
            raise ConfigError("Le contrat thermique prévoit 37 °C et un seuil de départ à 35 °C.")
        if not c.enclosure_limit_c > c.setpoint_c + c.hysteresis_c:
            raise ConfigError("Le seuil limite de l'enceinte doit dépasser la régulation.")
        if c.cpu_cutoff_c <= c.cpu_warning_c:
            raise ConfigError("La coupure CPU doit être supérieure au seuil d'alerte.")
        if not 0 < c.temperature_poll_s <= 10:
            raise ConfigError("Cadence de température invalide.")
        # Intensité LED validée pour le laboratoire : maximum 10 %.
        if not 0 < c.led_brightness <= 0.10:
            raise ConfigError("Luminosité LED supérieure au maximum autorisé de 10 %.")
        if c.camera_interval_s != 300:
            raise ConfigError("La cadence prévue est une photo toutes les cinq minutes.")
        if c.shutdown_button_gpio is not None and (
            not isinstance(c.shutdown_button_gpio, int)
            or c.shutdown_button_gpio in {12, 21, 22}
            or not 2 <= c.shutdown_button_gpio <= 27
        ):
            raise ConfigError("GPIO du bouton invalide ou déjà réservé.")
        # Depuis l'ajout du bouton tactile, l'extinction Linux peut
        # fonctionner sans bouton GPIO physique. L'autorisation réelle
        # est imposée par safe_staging + passerelle systemd root dédiée.
        if c.shutdown_animation_s < 3.6:
            raise ConfigError("Conserver le temps nécessaire à l'animation d'extinction.")
        return c
