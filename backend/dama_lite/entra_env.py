"""Lecture locale et privée des identifiants Entra déjà installés sur le Pi.

Format existant /etc/dama-lite/graph.env : MS_TENANT_ID, MS_CLIENT_ID,
MS_CLIENT_SECRET, MS_DRIVE_ID et MS_FOLDER_ID. Jamais de secrets dans Git,
la configuration JSON, les journaux, les arguments CLI ou le résultat API.
"""
from __future__ import annotations

import stat
from pathlib import Path

from .config import ConfigError

_REQUIRED = {"MS_TENANT_ID", "MS_CLIENT_ID", "MS_CLIENT_SECRET", "MS_DRIVE_ID"}
_ALLOWED = _REQUIRED | {"MS_FOLDER_ID"}


def read_graph_env(path: str) -> dict[str, str]:
    source = Path(path)
    if not source.is_absolute():
        raise ConfigError("Le fichier Entra doit avoir un chemin absolu.")
    if source.is_symlink():
        raise ConfigError("Lien symbolique Entra refusé.")
    try:
        metadata = source.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ConfigError("Le fichier Entra doit être un fichier régulier.")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise ConfigError(
                "Permissions Entra trop larges : chmod 600 requis."
            )
        raw = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            "Fichier Entra introuvable ou inaccessible au service DAMA Lite."
        ) from exc
    parsed: dict[str, str] = {}
    for lineno, line in enumerate(raw.splitlines(), start=1):
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        if cleaned.startswith("export "):
            cleaned = cleaned[7:].strip()
        key, sep, value = cleaned.partition("=")
        key = key.strip()
        if sep != "=" or key not in _ALLOWED or key in parsed:
            raise ConfigError(f"Fichier Entra : champ non autorisé/dupliqué à la ligne {lineno}.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if not value:
            raise ConfigError(f"Fichier Entra : valeur vide pour {key}.")
        parsed[key] = value
    if _REQUIRED - parsed.keys():
        raise ConfigError(
            "Fichier Entra incomplet : identifiants requis absents."
        )
    return parsed
