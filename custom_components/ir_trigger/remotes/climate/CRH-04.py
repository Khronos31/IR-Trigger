# CHOFU CRH-04 (床暖対流ヒーター) IR protocol
#
# 10-byte message with custom 4-pulse preamble.
# All bytes use nibble-complement encoding: high nibble = bitwise complement of low nibble.
# Preamble: mark(3050) space(3050) mark(3050) space(4400)  [us]
# Bit timing: mark=550us, space-0=550us, space-1=1650us
#
# Byte map:
#   0: BC (fixed)
#   1: 43 (fixed)
#   2: fan mode high bits
#   3: operation mode  (F0=off, 78=heat, 3C=speed-heat)
#   4: fan mode low bits
#   5: temperature low nibble (bit-reversed offset from 10°C)
#   6: F0 (fixed)
#   7: temperature high bit
#   8: F0 (fixed)
#   9: ion  (F0=off, D2=on)

domain = "climate"
hvac_modes = ["heat", "fan_only", "off"]
fan_modes = ["パワー", "快適", "静か", "強", "中", "弱", "微", "対流", "速暖"]
preset_modes = ["Normal", "Ion"]
min_temp = 10
max_temp = 30
default_fan_mode = "快適"
default_temperature = 20.0


def _enc(v):
    v = v & 0xF
    return v | ((~v & 0xF) << 4)


def _rev4(n):
    return int(f"{n & 0xF:04b}"[::-1], 2)


_FAN_TABLE = {
    "対流":   (_enc(0), _enc(0)),
    "強":     (_enc(0), _enc(1)),
    "弱":     (_enc(1), _enc(0)),
    "快適":   (_enc(1), _enc(1)),
    "微":     (_enc(2), _enc(0)),
    "静か":   (_enc(2), _enc(1)),
    "中":     (_enc(3), _enc(0)),
    "パワー": (_enc(3), _enc(1)),
}


def encode(hvac_mode: str, fan_mode: str, temperature: float, preset: str) -> str:
    """Return CHOFU-<hex> IR code string for the given climate state."""
    ion = (preset == "Ion")

    if hvac_mode == "off":
        # Complete power-off: ion always cleared
        data = bytes([0xBC, 0x43, _enc(0), _enc(0), _enc(0), _enc(0),
                      0xF0, _enc(0), 0xF0, _enc(0)])

    elif hvac_mode == "fan_only":
        # Ion-only mode: heater stopped, ion generator running
        data = bytes([0xBC, 0x43, _enc(0), _enc(0), _enc(0), _enc(0),
                      0xF0, _enc(0), 0xF0, _enc(2)])

    elif fan_mode == "速暖":
        data = bytes([0xBC, 0x43, _enc(0), _enc(12), _enc(0), _enc(0),
                      0xF0, _enc(0), 0xF0, _enc(2) if ion else _enc(0)])

    else:
        b2, b4 = _FAN_TABLE.get(fan_mode, (_enc(0), _enc(1)))
        if fan_mode == "対流":
            b5, b7 = _enc(0), _enc(0)
        else:
            offset = max(0, min(20, int(temperature) - 10))
            b5 = _enc(_rev4(offset & 0xF))
            b7 = _enc((offset >> 4) & 0xF)
        b9 = _enc(2) if ion else _enc(0)
        data = bytes([0xBC, 0x43, b2, _enc(8), b4, b5, 0xF0, b7, 0xF0, b9])

    return "CHOFU-" + data.hex().upper()
