import asyncio
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "ir_trigger"
    / "physical_sync.py"
)
SPEC = importlib.util.spec_from_file_location("ir_trigger_physical_sync", MODULE_PATH)
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)


class PhysicalSyncGuardTest(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.guard = SYNC.PhysicalSyncGuard(
            clock=lambda: self.now,
            echo_window=1.0,
            duplicate_window=0.3,
        )

    def test_local_transmission_echo_is_rejected_only_for_local_receiver(self):
        self.guard.record_transmission("CODE", ["rx_bedroom"])
        self.assertEqual(
            self.guard.classify_received("rx_bedroom", "CODE"),
            "echo",
        )
        self.assertEqual(
            self.guard.classify_received("rx_living", "CODE"),
            "accepted",
        )

    def test_expired_transmission_is_accepted(self):
        self.guard.record_transmission("CODE", ["rx_bedroom"])
        self.now += 1.01
        self.assertEqual(
            self.guard.classify_received("rx_bedroom", "CODE"),
            "accepted",
        )

    def test_duplicate_is_scoped_by_receiver_and_code(self):
        self.assertEqual(self.guard.classify_received("rx_a", "CODE"), "accepted")
        self.now += 0.2
        self.assertEqual(self.guard.classify_received("rx_a", "CODE"), "duplicate")
        self.assertEqual(self.guard.classify_received("rx_b", "CODE"), "accepted")
        self.assertEqual(self.guard.classify_received("rx_a", "OTHER"), "accepted")
        self.now += 0.31
        self.assertEqual(self.guard.classify_received("rx_a", "CODE"), "accepted")

    def test_tracking_transmitter_records_before_delegate(self):
        observations = []

        class Transmitter:
            async def async_send(inner_self, code):
                observations.append(self.guard.classify_received("rx_a", code))
                return "sent"

        transmitter = SYNC.PhysicalSyncTrackingTransmitter(
            Transmitter(), self.guard, ["rx_a"]
        )
        result = asyncio.run(transmitter.async_send("CODE"))
        self.assertEqual(result, "sent")
        self.assertEqual(observations, ["echo"])


class PhysicalSyncConfigTest(unittest.TestCase):
    def test_opt_in_requires_receiver_scope(self):
        with self.assertRaisesRegex(ValueError, "requires receiver"):
            SYNC.validate_receiver_scope(True, None, "Light_Bedroom")
        with self.assertRaisesRegex(ValueError, "requires receiver"):
            SYNC.validate_receiver_scope(True, [], "Light_Bedroom")

    def test_receiver_scope_accepts_string_or_list(self):
        self.assertEqual(
            SYNC.validate_receiver_scope(True, "rx_a", "Device"),
            frozenset({"rx_a"}),
        )
        self.assertEqual(
            SYNC.validate_receiver_scope(True, ["rx_a", "rx_b"], "Device"),
            frozenset({"rx_a", "rx_b"}),
        )
        self.assertEqual(
            SYNC.validate_receiver_scope(False, None, "Device"),
            frozenset(),
        )


class LightStateSyncTest(unittest.TestCase):
    def test_mapping_derives_dedicated_on_and_off(self):
        actions = SYNC.build_light_sync_actions(
            {"FULL": "ON-CODE", "OFF": "OFF-CODE"},
            {"turn_on": "FULL", "turn_off": "OFF"},
            {},
        )
        self.assertEqual(actions, {"ON-CODE": "on", "OFF-CODE": "off"})

    def test_mapping_derives_toggle_when_on_and_off_share_code(self):
        actions = SYNC.build_light_sync_actions(
            {"POWER": "TOGGLE-CODE"},
            {"turn_on": "POWER", "turn_off": "POWER"},
            {},
        )
        self.assertEqual(actions, {"TOGGLE-CODE": "toggle"})

    def test_explicit_button_semantics_extend_derived_mapping(self):
        actions = SYNC.build_light_sync_actions(
            {"FULL": "ON-CODE", "OFF": "OFF-CODE", "NIGHT": "NIGHT-CODE"},
            {"turn_on": "FULL", "turn_off": "OFF"},
            {"NIGHT": "on", "FULL": "ignore"},
        )
        self.assertEqual(actions, {"OFF-CODE": "off", "NIGHT-CODE": "on"})

    def test_invalid_or_conflicting_semantics_fail(self):
        with self.assertRaisesRegex(ValueError, "invalid light sync action"):
            SYNC.build_light_sync_actions(
                {"POWER": "CODE"}, {}, {"POWER": "dim"}
            )
        with self.assertRaisesRegex(ValueError, "conflicting light sync actions"):
            SYNC.build_light_sync_actions(
                {"A": "CODE", "B": "CODE"}, {}, {"A": "on", "B": "off"}
            )

    def test_apply_light_action(self):
        self.assertTrue(SYNC.apply_light_sync_action(False, "on"))
        self.assertFalse(SYNC.apply_light_sync_action(True, "off"))
        self.assertFalse(SYNC.apply_light_sync_action(True, "toggle"))
        self.assertTrue(SYNC.apply_light_sync_action(False, "toggle"))
        self.assertIsNone(SYNC.apply_light_sync_action(True, "ignore"))


if __name__ == "__main__":
    unittest.main()
