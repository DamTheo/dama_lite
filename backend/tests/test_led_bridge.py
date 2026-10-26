"""Contrôle LED hors GPIO, avec un faux bandeau de 64 LED."""
import unittest

from dama_lite.led_bridge import (
    PulseAnimator, StatusCache, gentle_pulse_factor,
    selected_available_slot, states_from_snapshot, selftest, should_hold_previous,
)
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

    def test_selection_does_not_suppress_red_or_yellow(self):
        data = {
            "power": "on", "ui_selected_camera": 7,
            "thermal": {"fault": None},
            "cameras": [
                {"slot": n, "configured": True, "connected": True,
                 "health": "available"} for n in range(1, 9)
            ],
        }
        data["cameras"][6]["connected"] = False
        self.assertEqual(7, selected_available_slot(
            data, states_from_snapshot(data)
        ))
        data["cameras"][6]["connected"] = True
        data["cameras"][6]["health"] = "running"
        self.assertEqual(7, selected_available_slot(
            data, states_from_snapshot(data)
        ))

    def test_short_http_timeout_does_not_flicker_but_long_loss_goes_off(self):
        self.assertFalse(should_hold_previous(None, 10.0))
        self.assertTrue(should_hold_previous(100.0, 102.99))
        self.assertFalse(should_hold_previous(100.0, 103.0))
        self.assertFalse(should_hold_previous(100.0, 104.5))

    def test_soft_selection_blinks_including_running_and_fault(self):
        data = {
            "power": "on", "ui_selected_camera": 3,
            "thermal": {"fault": None},
            "cameras": [{
                "slot": slot, "configured": True, "connected": True,
                "health": "available",
            } for slot in range(1, 9)],
        }
        states = states_from_snapshot(data)
        self.assertEqual(3, selected_available_slot(data, states))
        data["cameras"][2]["health"] = "running"
        states = states_from_snapshot(data)
        self.assertEqual(3, selected_available_slot(data, states))
        data["cameras"][2]["health"] = "fault"
        self.assertEqual(3, selected_available_slot(data, states_from_snapshot(data)))
        data["cameras"][2]["health"] = "available"
        data["led_blackout"] = True
        self.assertIsNone(selected_available_slot(data, states_from_snapshot(data)))
        data["led_blackout"] = False
        data["ui_selected_camera"] = True
        self.assertIsNone(selected_available_slot(data, states_from_snapshot(data)))

    def test_pulse_never_exceeds_global_brightness_limit(self):
        from math import isclose
        self.assertTrue(isclose(gentle_pulse_factor(0), 1.0))
        samples = [gentle_pulse_factor(index * 0.05) for index in range(120)]
        self.assertLessEqual(min(samples), 0.021)
        self.assertGreaterEqual(min(samples), 0.0)
        self.assertLessEqual(max(samples), 1.0)
        strip = SimulatedPixels()
        controller = LightController(
            enabled=False, gpio=12, brightness=.1, driver=strip
        )
        controller.update(["available"] * 8, pulse_slot=3, pulse_factor=0.20)
        self.assertEqual([(0, 255, 0)] * 8, strip.colors[:8])
        self.assertEqual([(0, 51, 0)] * 8, strip.colors[16:24])
        self.assertEqual([(0, 255, 0)] * 8, strip.colors[24:32])
        controller.update(
            ["available", "available", "fault"] + ["available"] * 5,
            pulse_slot=3, pulse_factor=0.2,
        )
        self.assertEqual([(51, 0, 0)] * 8, strip.colors[16:24])
        controller.update(
            ["available", "available", "running"] + ["available"] * 5,
            pulse_slot=3, pulse_factor=0.2,
        )
        self.assertEqual([(51, 34, 0)] * 8, strip.colors[16:24])
        with self.assertRaises(ValueError):
            controller.update(["available"] * 8, pulse_slot=3, pulse_factor=1.2)
        controller.close()

    def test_high_contrast_pulse_and_global_brightness_limit(self):
        self.assertAlmostEqual(1.0, gentle_pulse_factor(0))
        self.assertAlmostEqual(0.02, gentle_pulse_factor(1.2))
        self.assertAlmostEqual(1.0, gentle_pulse_factor(2.4))
        strip = SimulatedPixels()
        driver = LightController(False, 12, 0.10, driver=strip)
        driver.update(["running"] + ["available"] * 7,
                      pulse_slot=1, pulse_factor=0.02)
        self.assertEqual([(5, 3, 0)] * 8, strip.colors[:8])
        self.assertEqual([(0, 255, 0)] * 8, strip.colors[8:16])
        driver.close()

    def test_25hz_pulse_is_continuous_and_fades_out(self):
        animator = PulseAnimator()
        slot, factor = animator.frame(5, 100.0)
        self.assertEqual((5, 1.0), (slot, factor))
        previous = factor
        for index in range(1, 51):
            slot, factor = animator.frame(5, 100.0 + 0.04 * index)
            self.assertEqual(5, slot)
            self.assertLess(abs(factor - previous), .055)
            previous = factor
        slot, factor = animator.frame(None, 102.0)
        self.assertEqual(5, slot)
        self.assertAlmostEqual(previous, factor, delta=.02)
        slot, factor = animator.frame(None, 102.4)
        self.assertEqual((None, 1.0), (slot, factor))

    def test_http_cache_does_not_stall_pwm_and_expires_safely(self):
        cache = StatusCache()
        self.assertIsNone(cache.read(100.0))
        data = {"power": "on"}
        cache.publish(data, 100.0)
        self.assertIs(cache.read(102.95), data)
        self.assertIsNone(cache.read(103.0))

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
