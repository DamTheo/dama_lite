"""Essai complet du régulateur dans un relais purement simulé.

Aucune écriture GPIO et aucune création d'autorisation de chauffe.
Les séquences sont des températures injectées, pas une montée physique.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dama_lite.config import Config
from dama_lite.thermal import SensorError, ThermalController


class VirtualSensor:
    def __init__(self, temperature=21.687):
        self.temperature = temperature

    def read(self):
        if self.temperature is None:
            raise SensorError("SONDE_DEBRANCHEE")
        return self.temperature


class VirtualRelay:
    def __init__(self):
        self.on = False
        self.history = []

    def set(self, state):
        self.on = bool(state)
        self.history.append(self.on)

    def close(self):
        self.on = False


class HeatRampTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        path = Path(self.tempdir.name) / "config.json"
        path.write_text('{"heating_enabled": true, "setpoint_c": 37.0, '
                        '"start_min_c": 35.0, "hysteresis_c": 0.3, '
                        '"enclosure_limit_c": 41.0}', encoding="utf-8")
        cfg = Config.load(path)
        self.sensor = VirtualSensor()
        self.relay = VirtualRelay()
        self.cpu = 47.0
        # La fausse sortie est injectée : aucune commande matérielle GPIO.
        with patch("dama_lite.thermal.GPIORelay",
                   side_effect=AssertionError("GPIO interdit dans les tests")):
            self.ctrl = ThermalController(
                cfg, sensor=self.sensor, relay=self.relay,
                cpu_reader=lambda: self.cpu,
            )

    def tearDown(self):
        self.ctrl.stop()
        self.assertFalse(self.relay.on)
        self.tempdir.cleanup()

    def step(self, temperature, heater, ready, fault=None):
        self.sensor.temperature = temperature
        self.ctrl.tick()
        state = self.ctrl.snapshot()
        self.assertEqual(
            heater, self.relay.on, f"commande relais à {temperature} °C"
        )
        self.assertEqual(heater, state["heater_on"])
        self.assertEqual(ready, state["ready"])
        self.assertEqual(fault, state["fault"])
        return state

    def test_warmup_35_gate_37_point_3_cut_38_overshoot_and_restart(self):
        # La séquence est INJECTÉE, pas une prédiction de la température
        # que la véritable enceinte atteindra.
        sequence = (
            (21.687, True, False),
            (34.9, True, False),
            (35.0, True, True),
            (36.69, True, True),
            (37.0, True, True),
            (37.29, True, True),
            (37.31, False, True),
            (37.8, False, True),
            (38.0, False, True),
            (37.0, False, True),
            (36.71, False, True),
            (36.69, True, True),
            (37.31, False, True),
        )
        for temp, relay_on, ready in sequence:
            with self.subTest(temperature_c=temp):
                self.step(temp, relay_on, ready)
        self.assertGreater(len(self.relay.history), 10)

    def test_chamber_cutoff_41_is_latched_even_after_cooling(self):
        self.step(35.2, True, True)
        self.step(41.0, False, False, "SURCHAUFFE_ENCEINTE")
        self.step(36.0, False, False, "SURCHAUFFE_ENCEINTE")

    def test_cpu_warning_at_65_and_latched_shutdown_at_80(self):
        self.step(35.2, True, True)
        self.cpu = 65.0
        state = self.step(35.2, True, True)
        self.assertTrue(state["cpu_warning"])
        self.cpu = 80.0
        self.step(35.2, False, False, "SURCHAUFFE_RASPBERRY")
        self.cpu = 45.0
        self.step(35.2, False, False, "SURCHAUFFE_RASPBERRY")

    def test_missing_cpu_sensor_cuts_latches_and_never_restarts(self):
        self.step(21.687, True, False)
        self.cpu = None
        self.step(21.687, False, False, "SONDE_CPU_INDISPONIBLE")
        self.cpu = 45.0
        self.step(21.687, False, False, "SONDE_CPU_INDISPONIBLE")

    def test_missing_chamber_sensor_cuts_latches_and_never_restarts(self):
        self.step(21.687, True, False)
        self.sensor.temperature = None
        self.ctrl.tick()
        self.assertFalse(self.relay.on)
        self.assertFalse(self.ctrl.snapshot()["ready"])
        self.assertIn("SONDE", self.ctrl.snapshot()["fault"])
        self.sensor.temperature = 35.8
        self.ctrl.tick()
        self.assertFalse(self.relay.on)
        self.assertFalse(self.ctrl.snapshot()["ready"])


if __name__ == "__main__":
    unittest.main()
