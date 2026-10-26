"""Contrôle LED hors GPIO, avec un faux bandeau de 64 LED."""
import unittest

from dama_lite.led_bridge import states_from_snapshot, selftest
from dama_lite.lights import LightController


class SimulatedPixels:
    def __init__(self):
        self.colors = [(0, 0, 0)] * 64
        self.seen = []

    def __setitem__(self, i, value):
        self.colors[i] = value

    def show(self):
        self.seen.append(list(self.colors))


class LedBridgeTests(unittest.TestCase):
    def test_eight_live_cameras_green_even_if_heat_not_yet_on(self):
        data = {
            "power": "on",
            "thermal": {"fault": None, "heating_enabled": False},
            "cameras": [{
                "slot": n, "configured": True,
                "connected": True, "health": "available",
            } for n in range(1, 9)],
        }
        self.assertEqual(["available"] * 8, states_from_snapshot(data))
        data["thermal"]["fault"] = "DS18B20"
        self.assertEqual(["fault"] * 8, states_from_snapshot(data))

    def test_per_slot_fault_and_running_colors_without_heating(self):
        data = {
            "power": "on",
            "thermal": {"fault": None, "heating_enabled": False},
            "cameras": [{
                "slot": slot, "configured": True, "connected": True,
                "health": "available",
            } for slot in range(1, 9)],
        }
        data["cameras"][1]["health"] = "running"
        data["cameras"][4]["health"] = "fault"
        data["cameras"][6]["connected"] = False
        self.assertEqual(
            ["available", "running", "available", "available",
             "fault", "available", "fault", "available"],
            states_from_snapshot(data),
        )

    def test_leds_off_if_status_incomplete(self):
        self.assertEqual(["off"] * 8, states_from_snapshot({"power": "on"}))

    def test_selftest_exactly_eight_segments_and_off(self):
        strip = SimulatedPixels()
        controller = LightController(enabled=False, gpio=12,
                                     brightness=0.10, driver=strip)
        import unittest.mock
        with unittest.mock.patch("dama_lite.led_bridge.time.sleep"):
            selftest(controller)
        for i in range(8):
            self.assertEqual([(0, 255, 0)] * 8,
                             strip.seen[i+1][i*8:i*8+8])
        self.assertEqual([(0, 0, 0)] * 64, strip.seen[-1])
        controller.close()


if __name__ == "__main__":
    unittest.main()
