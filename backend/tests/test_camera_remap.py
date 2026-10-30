"""Les huit ports USB restent uniques ; CAM1/CAM2 ont ete permutees."""
import unittest
from dama_lite.camera_remap import (
    remap_staging, usb_port, USB_PORT_FOR_LOGICAL_SLOT, UNVERIFIED_SLOTS,
)


def make_raw():
    prefix = "/dev/v4l/by-path/platform-fd500000.pcie-pci-0000:01:00.0-usb-0:"
    ports = ("1.2.4", "1.2.3", "1.2.2", "1.2.1",
             "1.1.1", "1.1.2", "1.1.3", "1.1.4")
    return {
        "cameras": [
            {"slot": i, "device": prefix + port + ":1.0-video-index0"}
            for i, port in enumerate(ports, 1)
        ],
        "heating_enabled": False,
        "leds_enabled": False,
        "allow_os_shutdown": True,
        "sharepoint": {"graph_env_path": "/etc/dama-lite/graph.env"},
    }


class MappingTests(unittest.TestCase):
    def test_full_eight_port_bijective_mapping(self):
        original = make_raw()
        revised = remap_staging(original)
        expected = [USB_PORT_FOR_LOGICAL_SLOT[i] for i in range(1, 9)]
        self.assertEqual(
            expected, [usb_port(c["device"]) for c in revised["cameras"]]
        )
        self.assertEqual(8, len(set(c["device"] for c in revised["cameras"])))
        self.assertEqual(set(), set(UNVERIFIED_SLOTS))
        self.assertTrue(all(c["mapping_verified"] for c in revised["cameras"]))
        self.assertEqual(original["sharepoint"], revised["sharepoint"])
        self.assertEqual(original, make_raw())
        self.assertEqual(revised, remap_staging(revised))

    def test_swap_only_first_two_ports_from_previous_deployment(self):
        existing = make_raw()
        previous_ports = [
            "1.1.3", "1.1.4", "1.1.2", "1.1.1",
            "1.2.4", "1.2.3", "1.2.2", "1.2.1",
        ]
        head = existing["cameras"][0]["device"].split("1.2.4:")[0]
        for cam, port in zip(existing["cameras"], previous_ports):
            cam["device"] = head + port + ":1.0-video-index0"
            cam["mapping_verified"] = cam["slot"] != 2
        new = remap_staging(existing)
        self.assertEqual("1.1.4", usb_port(new["cameras"][0]["device"]))
        self.assertEqual("1.1.3", usb_port(new["cameras"][1]["device"]))
        self.assertTrue(new["cameras"][0]["mapping_verified"])
        self.assertTrue(new["cameras"][1]["mapping_verified"])
        self.assertEqual(
            [c["device"] for c in existing["cameras"][2:]],
            [c["device"] for c in new["cameras"][2:]],
        )

    def test_reject_duplicate_or_unexpected_port(self):
        old = make_raw()
        old["cameras"][7]["device"] = old["cameras"][6]["device"]
        with self.assertRaisesRegex(ValueError, "invalides"):
            remap_staging(old)
        old = make_raw()
        old["cameras"][7]["device"] = old["cameras"][7]["device"].replace(
            "1.1.4", "1.3.4"
        )
        with self.assertRaisesRegex(ValueError, "invalides"):
            remap_staging(old)

    def test_by_id_is_not_unique(self):
        self.assertIsNone(usb_port(
            "/dev/v4l/by-id/usb-DSJ_UC60_Video_200901010001-video-index0"
        ))


if __name__ == "__main__":
    unittest.main()
