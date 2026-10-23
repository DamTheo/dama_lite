import unittest

from dama_lite.lights import LightController, pixel_colors


class FakeStrip:
    def __init__(self):
        self.colors = [(0, 0, 0)] * 64
        self.calls = 0

    def __setitem__(self, key, value):
        self.colors[key] = value

    def show(self):
        self.calls += 1


class LedTests(unittest.TestCase):
    def test_eight_leds_per_slot(self):
        colors = pixel_colors(["available", "running", "fault"] + ["off"] * 5)
        self.assertEqual(64, len(colors))
        self.assertEqual([(0, 255, 0)] * 8, colors[:8])
        self.assertEqual([(255, 170, 0)] * 8, colors[8:16])
        self.assertEqual([(255, 0, 0)] * 8, colors[16:24])

    def test_no_leds_during_photo(self):
        strip = FakeStrip()
        leds = LightController(False, 12, .1, driver=strip)
        leds.update(["running"] * 8)
        leds.blackout_on()
        self.assertEqual([(0, 0, 0)] * 64, strip.colors)
        leds.update(["available"] * 8)
        self.assertEqual([(0, 0, 0)] * 64, strip.colors)
        leds.blackout_off()
        self.assertEqual([(0, 255, 0)] * 64, strip.colors)
        leds.close()


if __name__ == "__main__":
    unittest.main()
