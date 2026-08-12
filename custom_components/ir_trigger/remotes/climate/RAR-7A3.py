"""Hitachi RAR-7A3 full-state AEHA climate protocol.

Supported indoor-unit families include the RAS-V22E/V25E/V28E/V36E/V40E2
models documented for the RAR-7A3 remote. Bytes after the three-byte prefix
are stored as value/complement pairs.
"""

domain = "climate"
hvac_modes = ["cool", "heat", "dry", "auto", "off"]
fan_modes = ["auto", "1", "2", "3", "4", "5"]
preset_modes = ["normal", "eco", "save", "eco_save"]
min_temp = 10
max_temp = 32
default_fan_mode = "auto"
default_temperature = 25.0
default_temperatures = {
    "cool": 25.0,
    "heat": 18.0,
    "dry": 25.0,
    "auto": 0.0,
}
temperature_ranges = {
    "cool": (16.0, 32.0),
    "heat": (16.0, 32.0),
    "dry": (10.0, 32.0),
    "ryokai": (16.0, 32.0),
    "auto": (-3.0, 3.0),
}

# These actions preserve the current full climate state and change only the
# command byte(s). IR-Trigger exposes them as companion button entities.
climate_buttons = {
    "涼快": "set_ryokai",
    "上下スイング": "vertical_swing",
    "左右スイング": "horizontal_swing",
    "フィルター掃除": "filter_clean",
}
climate_button_states = {
    "set_ryokai": {
        "hvac_mode": "dry",
        "protocol_mode": "ryokai",
        "fan_mode": "1",
        "temperature": 25.0,
    },
}
preset_start_modes = {
    "eco": "auto",
    "eco_save": "auto",
}
clear_eco_on_hvac_mode = True

_MODE_ENCODE = {
    "cool": 0x03,
    "ryokai": 0x04,
    "dry": 0x05,
    "heat": 0x06,
    "auto": 0x07,
}
_MODE_DECODE = {value: key for key, value in _MODE_ENCODE.items()}

_FAN_ENCODE = {
    "1": 0x10,
    "2": 0x20,
    "3": 0x30,
    "4": 0x40,
    "auto": 0x50,
    "5": 0x60,
}
_FAN_DECODE = {value >> 4: key for key, value in _FAN_ENCODE.items()}

_PRIMARY_DEFAULTS = {
    3: 0x40,
    5: 0xFF,
    7: 0xCC,
    9: 0x92,
    11: 0x13,
    13: 0x64,
    15: 0x00,
    17: 0x00,
    19: 0x00,
    21: 0x00,
    23: 0x00,
    25: 0x53,
    27: 0xF1,
    29: 0x00,
    31: 0x00,
    33: 0x80,
    35: 0x03,
    37: 0x01,
    39: 0xA8,
    41: 0x00,
    43: 0x00,
    45: 0xFF,
    47: 0xFF,
    49: 0xFF,
    51: 0xFF,
    53: 0x00,
    55: 0x00,
}


def _preset_flags(preset: str | None) -> tuple[bool, bool]:
    """Return (eco, save) for a Home Assistant preset name."""
    value = preset or "normal"
    return value in ("eco", "eco_save"), value in ("save", "eco_save")


def _preset_name(eco: bool, save: bool) -> str:
    if eco and save:
        return "eco_save"
    if eco:
        return "eco"
    if save:
        return "save"
    return "normal"


def _operation(action: str | None) -> int:
    return {
        "temperature_up": 0x44,
        "temperature_down": 0x43,
        "set_fan_mode": 0x42,
        "set_save": 0x42,
        "set_eco": 0xA4,
        "vertical_swing": 0x81,
        "horizontal_swing": 0x05,
        "filter_clean": 0x65,
    }.get(action, 0x13)


def _auxiliary(action: str | None, hvac_mode: str, fan_mode: str, eco: bool) -> int:
    if action == "horizontal_swing":
        return 0xB2
    if action == "filter_clean":
        return 0xA6
    if action == "set_eco" or hvac_mode == "auto" or eco:
        return 0xA8
    if hvac_mode == "ryokai":
        return 0x99
    if fan_mode == "5":
        return 0xA9
    if action == "set_fan_mode" and fan_mode == "1":
        return 0x98
    return 0x92


def _build(primary: dict[int, int]) -> bytes:
    data = bytearray(57)
    data[0:3] = b"\x01\x10\x00"
    values = dict(_PRIMARY_DEFAULTS)
    values.update(primary)
    for offset in range(3, 56, 2):
        value = values[offset] & 0xFF
        data[offset] = value
        data[offset + 1] = value ^ 0xFF
    return bytes(data)


def encode(
    hvac_mode: str,
    fan_mode: str | None,
    temperature: float,
    preset: str | None,
    action: str | None = None,
    protocol_mode: str | None = None,
) -> str:
    """Return an ``AEHA-<hex>`` RAR-7A3 full-state frame.

    ``action`` identifies the Home Assistant action that initiated this state
    change. RAR-7A3 includes the last remote-key operation in its full-state
    payload, so final state alone is insufficient for exact reproduction.
    """
    mode = str(hvac_mode)
    retained_mode = protocol_mode if protocol_mode in _MODE_ENCODE else None
    if mode == "off":
        active_mode = retained_mode or "cool"
    elif mode == "dry" and retained_mode == "ryokai":
        active_mode = "ryokai"
    else:
        active_mode = mode
    if active_mode not in _MODE_ENCODE:
        raise ValueError(f"Unsupported RAR-7A3 HVAC mode: {hvac_mode}")

    fan = fan_mode or "auto"
    if fan not in _FAN_ENCODE:
        raise ValueError(f"Unsupported RAR-7A3 fan mode: {fan_mode}")

    eco, save = _preset_flags(preset)
    mode_byte = _MODE_ENCODE[active_mode]
    fan_mode_byte = _FAN_ENCODE[fan] | mode_byte

    if active_mode == "auto":
        adjustment = max(-3, min(3, round(float(temperature))))
        temperature_byte = adjustment + 4
    else:
        low, high = temperature_ranges[active_mode]
        value = max(low, min(high, float(temperature)))
        temperature_byte = round(value * 4)

    # Power is bit 4. Save is represented by clearing bit 0 and may coexist
    # with either power state.
    power_save = 0xF1 if mode != "off" else 0xE1
    if save:
        power_save &= 0xFE

    feature_flags = 0x02 if eco else 0x00
    if fan == "5":
        feature_flags |= 0x30

    operation_action = "set_eco" if action == "set_hvac_mode" and active_mode == "auto" else action
    primary = {
        9: _auxiliary(action, active_mode, fan, eco),
        11: _operation(operation_action),
        13: temperature_byte,
        25: fan_mode_byte,
        27: power_save,
        29: feature_flags,
        35: 0x53 if active_mode in ("dry", "ryokai") else 0x03,
    }
    return "AEHA-" + _build(primary).hex().upper()


def decode(code: str) -> dict | None:
    """Decode a validated RAR-7A3 AEHA state block into climate state.

    Physical RAR-7A3 remotes transmit the state in a multi-block frame. Some
    receivers expose only the first 284-bit block (with a ``-284`` suffix),
    while IR-Trigger's encoder emits the complete 456-bit representation.
    Every field needed by Home Assistant is present by byte 29, so accept a
    complete first block while still validating every received value/
    complement pair.
    """
    if not isinstance(code, str) or not code.startswith("AEHA-"):
        return None
    hex_payload = code[5:].split("-", 1)[0]
    try:
        data = bytes.fromhex(hex_payload)
    except ValueError:
        return None
    if len(data) < 30 or data[:3] != b"\x01\x10\x00":
        return None
    # A non-byte-aligned receiver block may end with the value half of a pair.
    # Validate all pairs that are actually present; fields consumed below are
    # covered because they precede byte 30.
    if any(
        data[offset + 1] != (data[offset] ^ 0xFF)
        for offset in range(3, len(data) - 1, 2)
    ):
        return None

    protocol_mode = _MODE_DECODE.get(data[25] & 0x0F)
    fan_mode = _FAN_DECODE.get(data[25] >> 4)
    if protocol_mode is None or fan_mode is None:
        return None

    is_on = bool(data[27] & 0x10)
    eco = bool(data[29] & 0x02)
    save = not bool(data[27] & 0x01)

    if protocol_mode == "auto":
        temperature = float(data[13] - 4)
    else:
        temperature = data[13] / 4.0

    # HA has no dedicated Ryokai mode. Report it as dry while preserving the
    # protocol-specific mode for diagnostics and future control extensions.
    hvac_mode = "off" if not is_on else ("dry" if protocol_mode == "ryokai" else protocol_mode)
    return {
        "hvac_mode": hvac_mode,
        "fan_mode": fan_mode,
        "temperature": temperature,
        "preset_mode": _preset_name(eco, save),
        "protocol_mode": protocol_mode,
        "operation": data[11],
    }
