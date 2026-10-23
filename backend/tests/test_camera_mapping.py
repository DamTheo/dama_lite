import unittest

from dama_lite.camera_mapping import propose_slot_mapping


class MappingTests(unittest.TestCase):
    def test_keeps_port_position_even_when_enumeration_order_changes(self):
        old = {1: "/dev/v4l/by-path/usb-port-b", 2: "/dev/v4l/by-path/usb-port-a"}
        new = propose_slot_mapping(
            old, ["/dev/v4l/by-path/usb-port-a", "/dev/v4l/by-path/usb-port-b"]
        )
        self.assertEqual(old[1], new[1])
        self.assertEqual(old[2], new[2])

    def test_reassigns_disconnected_port_only_on_explicit_action(self):
        old = {1: "/dev/v4l/by-path/usb-port-old", 2: None}
        new = propose_slot_mapping(
            old, ["/dev/v4l/by-path/usb-port-2", "/dev/v4l/by-path/usb-port-4"]
        )
        self.assertEqual("/dev/v4l/by-path/usb-port-2", new[1])
        self.assertEqual("/dev/v4l/by-path/usb-port-4", new[2])
        self.assertIsNone(new[3])

    def test_rejects_ambiguous_ports(self):
        with self.assertRaises(ValueError):
            propose_slot_mapping({}, ["same"] * 2)
        with self.assertRaises(ValueError):
            propose_slot_mapping({}, [str(i) for i in range(9)])


if __name__ == "__main__":
    unittest.main()
