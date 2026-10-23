"""Interverrouillages logiciels préalables : aucune écriture GPIO.

Ce contrôle ne remplace PAS la vérification physique du relais ni le dispositif
thermique de sécurité indépendant. Un processus inconnu pourrait piloter GPIO21.
"""
from __future__ import annotations

from pathlib import Path

LEGACY_GPIO_SCRIPTS = frozenset({
    "Programme_complet.py",  # relais GPIO21 + 64 LED GPIO12
    "Programme.py",          # 64 LED GPIO12
    "Test_LED.py",           # 64 LED GPIO12
})


def legacy_gpio_processes(proc_root: Path = Path("/proc")) -> list[dict]:
    """Détecte uniquement les anciens programmes GPIO connus, en lecture seule."""
    conflicts: list[dict] = []
    try:
        pids = list(proc_root.iterdir())
    except (OSError, PermissionError):
        return conflicts
    for entry in pids:
        if not entry.name.isdecimal():
            continue
        try:
            arguments = (entry / "cmdline").read_bytes().split(b"\0")
        except (OSError, PermissionError):
            continue
        filenames = set()
        for raw in arguments:
            if not raw:
                continue
            # Ne jamais reproduire les arguments complets d'un processus dans
            # des journaux : ils pourraient contenir un mot de passe.
            name = Path(raw.decode("utf-8", errors="replace")).name
            filenames.add(name)
        for name in sorted(filenames & LEGACY_GPIO_SCRIPTS):
            conflicts.append({"pid": int(entry.name), "program": name})
    return sorted(conflicts, key=lambda item: (item["program"], item["pid"]))


def ensure_gpio_exclusive(heating_enabled: bool, leds_enabled: bool) -> None:
    if not (heating_enabled or leds_enabled):
        return
    conflicts = legacy_gpio_processes()
    if conflicts:
        programs = ", ".join(
            f"{c['program']} (PID {c['pid']})" for c in conflicts
        )
        raise RuntimeError(
            "Conflit GPIO : ancien programme actif : " + programs
            + ". Ne jamais lancer deux contrôleurs de chauffe/LED en parallèle."
        )
