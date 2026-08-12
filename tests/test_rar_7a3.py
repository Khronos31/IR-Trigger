import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "ir_trigger"
    / "remotes"
    / "climate"
    / "RAR-7A3.py"
)
SPEC = importlib.util.spec_from_file_location("rar_7a3", MODULE_PATH)
RAR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RAR)

CONVERTER_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "ir_trigger"
    / "converter.py"
)
CONVERTER_SPEC = importlib.util.spec_from_file_location("ir_trigger_converter", CONVERTER_PATH)
CONVERTER = importlib.util.module_from_spec(CONVERTER_SPEC)
CONVERTER_SPEC.loader.exec_module(CONVERTER)


COOL_25_AUTO_ON = (
    "01100040BFFF00CC33926D13EC649B00FF00FF00FF00FF00FF53ACF10E00FF00FF"
    "807F03FC01FEA85700FF00FFFF00FF00FF00FF0000FF00FF"
)
HEAT_18_AUTO_ON = (
    "01100040BFFF00CC33926D13EC48B700FF00FF00FF00FF00FF56A9F10E00FF00FF"
    "807F03FC01FEA85700FF00FFFF00FF00FF00FF0000FF00FF"
)
AUTO_ECO_MINUS_1 = (
    "01100040BFFF00CC33A857A45B03FC00FF00FF00FF00FF00FF17E8F10E02FD00FF"
    "807F03FC01FEA85700FF00FFFF00FF00FF00FF0000FF00FF"
)
AUTO_SAVE_PLUS_1 = (
    "01100040BFFF00CC33A857A45B05FA00FF00FF00FF00FF00FF17E8F00F00FF"
    "00FF807F03FC01FEA85700FF00FFFF00FF00FF00FF0000FF00FF"
)
RYOKAI_25_FAN_1 = (
    "01100040BFFF00CC33996613EC649B00FF00FF00FF00FF00FF14EBF10E00FF"
    "00FF807F53AC01FEA85700FF00FFFF00FF00FF00FF0000FF00FF"
)


class RAR7A3ProtocolTest(unittest.TestCase):
    def test_template_models_contextual_eco_behavior(self):
        self.assertEqual(RAR.preset_start_modes["eco"], "auto")
        self.assertTrue(RAR.clear_eco_on_hvac_mode)

    def test_encode_captured_cool_frame(self):
        self.assertEqual(
            RAR.encode("cool", "auto", 25, "normal", "set_hvac_mode"),
            "AEHA-" + COOL_25_AUTO_ON,
        )

    def test_encode_captured_heat_frame(self):
        self.assertEqual(
            RAR.encode("heat", "auto", 18, "normal", "set_hvac_mode"),
            "AEHA-" + HEAT_18_AUTO_ON,
        )

    def test_encode_captured_ryokai_frame(self):
        self.assertEqual(
            RAR.encode(
                "dry", "1", 25, "normal", "set_ryokai", protocol_mode="ryokai"
            ),
            "AEHA-" + RYOKAI_25_FAN_1,
        )

    def test_encode_captured_auto_eco_frame(self):
        self.assertEqual(
            RAR.encode("auto", "1", -1, "eco", "set_eco"),
            "AEHA-" + AUTO_ECO_MINUS_1,
        )

    def test_encode_captured_auto_save_without_eco_frame(self):
        self.assertEqual(
            RAR.encode("auto", "1", 1, "save", "set_eco"),
            "AEHA-" + AUTO_SAVE_PLUS_1,
        )

    def test_temperature_operation_codes(self):
        up = bytes.fromhex(RAR.encode("cool", "auto", 26, "normal", "temperature_up")[5:])
        down = bytes.fromhex(RAR.encode("cool", "auto", 25, "normal", "temperature_down")[5:])
        self.assertEqual((up[11], up[13]), (0x44, 0x68))
        self.assertEqual((down[11], down[13]), (0x43, 0x64))

    def test_fan_modes_and_maximum_flags(self):
        expected = {"1": 0x13, "2": 0x23, "3": 0x33, "4": 0x43, "auto": 0x53, "5": 0x63}
        for fan, value in expected.items():
            with self.subTest(fan=fan):
                data = bytes.fromhex(RAR.encode("cool", fan, 25, "normal", "set_fan_mode")[5:])
                self.assertEqual(data[25], value)
        maximum = bytes.fromhex(RAR.encode("cool", "5", 25, "normal", "set_fan_mode")[5:])
        self.assertEqual((maximum[9], maximum[29]), (0xA9, 0x30))

    def test_eco_and_save_are_independent(self):
        data = bytes.fromhex(RAR.encode("auto", "1", 1, "eco_save", "set_save")[5:])
        self.assertEqual(data[27], 0xF0)
        self.assertEqual(data[29], 0x02)

    def test_stateless_commands(self):
        expected = {
            "vertical_swing": (0x92, 0x81),
            "horizontal_swing": (0xB2, 0x05),
            "filter_clean": (0xA6, 0x65),
        }
        for action, pair in expected.items():
            with self.subTest(action=action):
                data = bytes.fromhex(RAR.encode("cool", "auto", 25, "normal", action)[5:])
                self.assertEqual((data[9], data[11]), pair)

    def test_all_integrity_pairs_are_complements(self):
        data = bytes.fromhex(RAR.encode("auto", "5", 3, "eco_save", "set_fan_mode")[5:])
        self.assertEqual(len(data), 57)
        for offset in range(3, 56, 2):
            self.assertEqual(data[offset + 1], data[offset] ^ 0xFF)

    def test_decode_round_trip(self):
        for state in (
            ("cool", "auto", 25, "normal"),
            ("heat", "3", 22, "eco"),
            ("dry", "2", 20, "save"),
            ("auto", "1", -2, "eco_save"),
            ("off", "auto", 18, "normal"),
        ):
            with self.subTest(state=state):
                decoded = RAR.decode(RAR.encode(*state, action="set_hvac_mode"))
                self.assertEqual(decoded["hvac_mode"], state[0])
                self.assertEqual(decoded["fan_mode"], state[1])
                self.assertEqual(decoded["temperature"], float(state[2]))
                self.assertEqual(decoded["preset_mode"], state[3])

    def test_off_frame_retains_protocol_mode(self):
        decoded = RAR.decode(
            RAR.encode("off", "3", 22, "normal", "turn_off", protocol_mode="heat")
        )
        self.assertEqual(decoded["hvac_mode"], "off")
        self.assertEqual(decoded["protocol_mode"], "heat")

    def test_ryokai_is_preserved_as_protocol_mode(self):
        decoded = RAR.decode(
            RAR.encode("dry", "1", 25, "normal", "set_hvac_mode", protocol_mode="ryokai")
        )
        self.assertEqual(decoded["hvac_mode"], "dry")
        self.assertEqual(decoded["protocol_mode"], "ryokai")

    def test_decode_rejects_bad_complement(self):
        data = bytearray.fromhex(COOL_25_AUTO_ON)
        data[14] ^= 0x01
        self.assertIsNone(RAR.decode("AEHA-" + data.hex()))

    def test_converter_round_trip_preserves_456_bits(self):
        code = RAR.encode("cool", "4", 29, "eco_save", "temperature_up")
        raw = CONVERTER.code_to_raw(code)
        self.assertEqual(len(raw), 915)
        self.assertEqual(CONVERTER.raw_to_code(raw), code)


if __name__ == "__main__":
    unittest.main()
