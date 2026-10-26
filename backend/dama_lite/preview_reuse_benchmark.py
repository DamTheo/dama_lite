"""Mesure non invasive : premier JPEG froid puis reconnexion à chaud.

Une caméra à la fois : aucun hub n'est soumis à 8 flux simultanés.
Aucune acquisition scientifique, aucun accès SharePoint, aucun GPIO.
"""
from __future__ import annotations

import argparse
import http.client
import json
import time


def once(slot: int, timeout: float = 6.0) -> dict:
    conn = http.client.HTTPConnection("127.0.0.1", 8765, timeout=timeout)
    started = time.monotonic()
    try:
        conn.request("GET", f"/api/cameras/{slot}/stream")
        response = conn.getresponse()
        header_at = time.monotonic()
        one_byte = response.read(1) if response.status == 200 else b""
        return {
            "slot": slot,
            "http": response.status,
            "header_after_ms": round(1000 * (header_at - started)),
            "first_body_byte_after_ms": (
                round(1000 * (time.monotonic() - started)) if one_byte else None
            ),
        }
    except (OSError, http.client.HTTPException) as exc:
        return {
            "slot": slot,
            "http": None,
            "error": type(exc).__name__,
        }
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=1, choices=range(1, 9))
    args = ap.parse_args()
    # Deux connexions espacées de 200 ms : le deuxième passage doit
    # profiter du cache UVC de deux secondes.
    first = once(args.camera)
    time.sleep(0.2)
    second = once(args.camera)
    print(json.dumps({"cold": first, "warm": second}, ensure_ascii=False))
    if first.get("http") != 200 or second.get("http") != 200:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
