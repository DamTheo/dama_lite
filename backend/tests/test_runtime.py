"""Tests d'intégration locaux : aucune commande GPIO ni requête réseau réelle."""
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path

from dama_lite.config import CameraSpec, Config, SharePointConfig
from dama_lite.sessions import CannotStart, SessionManager
from dama_lite.store import Store


def settings(root: Path):
    return Config(
        host="127.0.0.1", port=8765, state_dir=root, ui_dir=root,
        sensor_id="28-0000006ca681", heating_enabled=True,
        relay_gpio=21, relay_active_high=True, setpoint_c=37,
        start_min_c=35, hysteresis_c=.3, enclosure_limit_c=41,
        cpu_warning_c=65, cpu_cutoff_c=80, temperature_poll_s=2,
        leds_enabled=False, led_gpio=12, led_brightness=.1,
        camera_interval_s=300, spool_limit_bytes=1000000,
        cameras=tuple(CameraSpec(slot=i, device=None) for i in range(1, 9)),
        sharepoint=SharePointConfig(), shutdown_button_gpio=None,
        allow_os_shutdown=False, shutdown_animation_s=4.8,
    )


class FakeThermal:
    def __init__(self, temp=35):
        self.temp = temp
        self.fault = None

    def snapshot(self):
        return {"ready": self.temp >= 35, "temperature_c": self.temp,
                "cpu_temperature_c": 41, "fault": self.fault, "heating_enabled": True}


class FakeCamera:
    def __init__(self, cfg):
        self.specs = {camera.slot: camera for camera in cfg.cameras}

    def ready(self, slot):
        return slot in range(1, 9)

    def photo(self, slot):
        return b"\x89PNG\r\n\x1a\nfake frame for test"


class FakeLights:
    def __init__(self):
        self.black = 0

    def blackout_on(self):
        self.black += 1

    def blackout_off(self):
        self.black -= 1

    def update(self, states):
        pass


class FakeSharePoint:
    def __init__(self):
        self.names = []

    def reserve_folder(self, name):
        self.names.append(name)
        return "folder-" + name, None


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.cfg = settings(self.root)
        self.store = Store(self.cfg.state_dir)
        self.thermal = FakeThermal()
        self.cam = FakeCamera(self.cfg)
        self.leds = FakeLights()
        self.graph = FakeSharePoint()
        self.manager = SessionManager(
            self.cfg, self.store, self.thermal, self.cam, self.leds, self.graph
        )

    def tearDown(self):
        self.manager.close()
        self.store.close()
        self.tempdir.cleanup()

    def test_mandatory_name_and_exact_graph_folder(self):
        for missing in (None, "", " ", "  "):
            with self.assertRaises(ValueError):
                self.manager.new_test(1, missing)
        self.assertEqual([], self.graph.names)
        item = self.manager.new_test(1, "Colonie A - Lot 1")
        self.assertEqual(["Colonie A - Lot 1"], self.graph.names)
        self.assertEqual("folder-Colonie A - Lot 1", item["folder_id"])
        self.assertEqual("Colonie A - Lot 1", item["name"])

    def test_heat_gate_and_exact_graph_folder(self):
        self.thermal.temp = 34.9
        with self.assertRaises(CannotStart):
            self.manager.new_test(1, "Ecoli-01")
        self.assertEqual([], self.graph.names)
        self.thermal.temp = 35.0
        item = self.manager.new_test(1, "Ecoli-01")
        self.assertEqual(["Ecoli-01"], self.graph.names)
        self.assertEqual("folder-Ecoli-01", item["folder_id"])
        self.manager._capture(item["id"])
        self.assertEqual(1, self.store.tests()[0]["images_count"])
        self.assertEqual(1, self.store.tests()[0]["pending_uploads"])
        self.assertEqual(0, self.leds.black)

    def test_slot_single_user_and_unique_test_name(self):
        self.manager.new_test(1, "Test-1")
        with self.assertRaises(CannotStart):
            self.manager.new_test(1, "Test-2")
        with self.assertRaises(CannotStart):
            self.manager.new_test(2, "Test-1")
        self.assertEqual(1, len(self.graph.names))

    def test_graph_reservation_does_not_block_status_or_other_slot(self):
        entered = threading.Event()
        release = threading.Event()
        errors = []

        def stalled(name):
            entered.set()
            if not release.wait(4):
                raise RuntimeError("Timeout test")
            return "folder-" + name, None

        self.graph.reserve_folder = stalled

        def create():
            try:
                self.manager.new_test(1, "Ecoli-long")
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=create, daemon=True)
        worker.start()
        self.assertTrue(entered.wait(2), "L'appel Graph n'a pas démarré")
        self.assertEqual(8, len(self.manager.led_states()))
        self.assertEqual("running", self.manager.led_states()[0])
        self.assertIsInstance(self.manager.overview(), list)
        with self.assertRaises(CannotStart):
            self.manager.new_test(1, "Ecoli-concurrent")
        with self.assertRaises(CannotStart):
            self.manager.new_test(2, "Ecoli-long")
        release.set()
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors)
        self.assertEqual("Ecoli-long", self.store.tests()[0]["name"])

    def test_graph_fails_without_leaking_slot_reservation(self):
        def failed(_name):
            raise RuntimeError("Graph indisponible")
        self.graph.reserve_folder = failed
        with self.assertRaises(RuntimeError):
            self.manager.new_test(1, "Ecoli-err")
        self.assertEqual([], self.manager.overview())
        self.assertEqual("available", self.manager.led_states()[0])
        self.assertEqual(set(), self.manager._reserving_slots)

    def test_camera_health_independent_of_global_sensor_fault(self):
        # Contrairement aux faux périphériques non configurés par défaut,
        # les huit canaux disposent ici d'un port USB explicitement associé.
        self.cam.specs = {
            slot: replace(self.cam.specs[slot], device=f"/dev/v4l/by-path/usb-slot-{slot}-video-index0")
            for slot in range(1, 9)
        }
        self.thermal.temp = 22
        self.thermal.fault = "SONDE_OU_RELAIS : CRC invalide"
        self.assertEqual(["available"] * 8, self.manager.camera_health_states())
        self.assertEqual(["fault"] * 8, self.manager.led_states())
        self.thermal.fault = None
        self.assertEqual(["off"] * 8, self.manager.led_states())
        self.assertEqual(["available"] * 8, self.manager.camera_health_states())

    def test_acknowledgement_preserves_error(self):
        item = self.manager.new_test(1, "Test-fail")
        self.store.set_state(item["id"], "fault", "Caméra débranchée")
        self.assertEqual("fault", self.manager.led_states()[0])
        with self.assertRaises(CannotStart):
            self.manager.new_test(1, "Autre")
        self.manager.acknowledge_camera(1)
        self.assertEqual("available", self.manager.led_states()[0])
        self.assertEqual("Caméra débranchée", self.store.tests()[0]["error"])
        self.assertEqual(1, self.store.tests()[0]["acknowledged"])

    def test_upload_failure_turns_led_red(self):
        item = self.manager.new_test(2, "Test-spool")
        self.manager._capture(item["id"])
        image = self.store.due_uploads()[0]
        self.store.mark_upload_failure(image["id"], 1, "Hors ligne")
        self.assertEqual("fault", self.manager.led_states()[1])


if __name__ == "__main__":
    unittest.main()
