import unittest
from pathlib import Path

from dama_lite.config import Config
from dama_lite.thermal import SensorError, ThermalController, heating_decision


class Sensor:
    def __init__(self, temp=22.0):
        self.temp = temp

    def read(self):
        if self.temp is None:
            raise SensorError("Sonde perdue")
        return self.temp


class Relay:
    def __init__(self):
        self.active = False
        self.history = []

    def set(self, value):
        self.active = bool(value)
        self.history.append(self.active)

    def close(self):
        self.active = False


def config(heating=True):
    # Éviter le matériel, injecter une fausse sortie relais.
    return Config(
        host="127.0.0.1", port=8765, state_dir=Path("/tmp/dama-lite-test"),
        ui_dir=Path("/tmp/dama-lite-ui"), sensor_id="28-0000006ca681",
        heating_enabled=heating, relay_gpio=21, relay_active_high=True,
        setpoint_c=37, start_min_c=35, hysteresis_c=.3,
        enclosure_limit_c=41, cpu_warning_c=65, cpu_cutoff_c=80,
        temperature_poll_s=2, leds_enabled=False, led_gpio=12,
        led_brightness=.1, camera_interval_s=300, spool_limit_bytes=100000,
        cameras=tuple(), sharepoint=None, shutdown_button_gpio=None,
        allow_os_shutdown=False, shutdown_animation_s=4.8,
    )


class ThermalTests(unittest.TestCase):
    def test_hysteresis(self):
        self.assertTrue(heating_decision(False, 36.6, 37, .3))
        self.assertFalse(heating_decision(False, 37.0, 37, .3))
        self.assertTrue(heating_decision(True, 37.1, 37, .3))
        self.assertFalse(heating_decision(True, 37.4, 37, .3))

    def test_35_gate_and_heat(self):
        sensor, relay = Sensor(22.0), Relay()
        control = ThermalController(config(), sensor, relay, cpu_reader=lambda: 41)
        control.tick()
        self.assertTrue(relay.active)
        self.assertFalse(control.snapshot()["ready"])
        sensor.temp = 35.0
        control.tick()
        self.assertTrue(control.snapshot()["ready"])
        sensor.temp = 37.31
        control.tick()
        self.assertFalse(relay.active)
        control.stop()

    def test_lost_sensor_latches_and_turns_off(self):
        sensor, relay = Sensor(32.0), Relay()
        control = ThermalController(config(), sensor, relay, cpu_reader=lambda: 40)
        control.tick()
        self.assertTrue(relay.active)
        sensor.temp = None
        control.tick()
        self.assertFalse(relay.active)
        self.assertIsNotNone(control.snapshot()["fault"])
        sensor.temp = 35.5
        control.tick()
        self.assertFalse(relay.active)
        self.assertFalse(control.snapshot()["ready"])
        control.stop()

    def test_cpu_warning(self):
        sensor, relay = Sensor(35.5), Relay()
        control = ThermalController(config(), sensor, relay, cpu_reader=lambda: 65.5)
        control.tick()
        self.assertTrue(control.snapshot()["cpu_warning"])
        control.stop()

    def test_overheat_blocks_restart(self):
        sensor, relay = Sensor(42.0), Relay()
        control = ThermalController(config(), sensor, relay, cpu_reader=lambda: 44)
        control.tick()
        self.assertFalse(relay.active)
        self.assertEqual(control.snapshot()["fault"], "SURCHAUFFE_ENCEINTE")
        control.stop()


if __name__ == "__main__":
    unittest.main()
