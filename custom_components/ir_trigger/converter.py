import logging
import math

_LOGGER = logging.getLogger(__name__)

# IR Protocol Constants (all values in microseconds)
# Based on AD00020P firmware (main.c) logic where time units are 0.1ms (100us)
# We convert them to us for our internal logic.

TOLERANCE = 0.30 # Increased tolerance for hardware variance

PROTOCOLS = {
    "NEC": {
        "leader_on": 9000,
        "leader_off": 4500,
        "bit_on": 560,
        "bit0_off": 560,
        "bit1_off": 1680,
        "threshold": 1200, # If OFF > 1200us, it's bit 1
    },
    "AEHA": { # KADEN
        "leader_on": 3200,
        "leader_off": 1600,
        "bit_on": 400,
        "bit0_off": 400,
        "bit1_off": 1200,
        "threshold": 800, # If OFF > 800us, it's bit 1
    },
    "SONY": {
        "leader_on": 2400,
        "leader_off": 600,
        "bit_on_0": 600,
        "bit_on_1": 1200,
        "bit_off": 600,
        "threshold": 900, # If ON > 900us, it's bit 1
    },
    "DAIKIN": {
        "leader_on": 4400,
        "leader_off": 2200,
        "bit_on": 400,
        "bit0_off": 400,
        "bit1_off": 1300,
        "threshold": 700, # If OFF > 700us, it's bit 1
    },
    "DAIKIN2": {
        "leader_on": 3000,
        "leader_off": 9000,
        "bit_on": 400,
        "bit0_off": 400,
        "bit1_off": 1300,
        "threshold": 700,
    }
}

def raw_to_code(raw: list[int]) -> str:
    """Convert raw pulse array to a hex string or RAW format based on main.c logic."""
    if not raw or len(raw) < 4:
        return ""

    # Try standard protocols with leader codes
    for name, config in PROTOCOLS.items():
        if name == "SONY":
            code = _decode_sony(raw, config)
        else:
            code = _decode_mark_space(raw, config)
        
        if code:
            return f"{name}_{code}"

    # Fallback to RAW format
    csv_pulses = ",".join(map(str, raw))
    return f"RAW_{csv_pulses}"

def code_to_raw(code: str) -> list[int]:
    """Convert code string back to RAW pulse array."""
    if code.startswith("RAW_"):
        try:
            return [int(x) for x in code[4:].split(",")]
        except ValueError:
            return []

    # Format check (e.g., NEC_XXXXXXXX)
    parts = code.split("_")
    if len(parts) != 2:
        return []

    name, hex_data = parts[0], parts[1]
    if name not in PROTOCOLS:
        return []

    config = PROTOCOLS[name]
    
    # Convert HEX to bits (LSB First as we did in _bits_to_hex)
    bits = []
    try:
        for i in range(0, len(hex_data), 2):
            byte_val = int(hex_data[i:i+2], 16)
            for b_idx in range(8):
                bits.append((byte_val >> b_idx) & 1)
    except ValueError:
        return []

    # Construct RAW array
    raw = [config["leader_on"], config["leader_off"]]
    
    if name == "SONY":
        for bit in bits:
            raw.append(config["bit_on_1"] if bit else config["bit_on_0"])
            raw.append(config["bit_off"])
    else:
        # NEC, AEHA, DAIKIN (Mark/Space)
        for bit in bits:
            raw.append(config["bit_on"])
            raw.append(config["bit1_off"] if bit else config["bit0_off"])
        # Append Stop Bit
        raw.append(config["bit_on"])

    return raw

def _is_match(actual: int, target: int) -> bool:
    """Check if actual pulse width is within tolerance of target."""
    return target * (1 - TOLERANCE) <= actual <= target * (1 + TOLERANCE)

def _decode_mark_space(raw: list[int], config: dict) -> str | None:
    """Generic decoder for Mark/Space protocols (NEC, AEHA, DAIKIN)."""
    if len(raw) < 10: return None # Very short signal
    
    # Leader check
    if not _is_match(raw[0], config["leader_on"]) or not _is_match(raw[1], config["leader_off"]):
        return None

    bits = []
    # Data starts from index 2
    for i in range(2, len(raw) - 1, 2):
        on_p = raw[i]
        off_p = raw[i+1]
        
        if not _is_match(on_p, config["bit_on"]):
            break # End of data or sync loss
        
        if off_p > 4000: # Abnormally long OFF is a gap (end of signal)
            break

        if off_p > config["threshold"]:
            bits.append(1)
        else:
            bits.append(0)

    if not bits: return None
    return _bits_to_hex(bits)

def _decode_sony(raw: list[int], config: dict) -> str | None:
    """SONY protocol decoder (Pulse width modulation on 'ON' state)."""
    if len(raw) < 10: return None
    
    if not _is_match(raw[0], config["leader_on"]) or not _is_match(raw[1], config["leader_off"]):
        return None

    bits = []
    for i in range(2, len(raw) - 1, 2):
        on_p = raw[i]
        off_p = raw[i+1]
        
        if not _is_match(off_p, config["bit_off"]):
            break
            
        if on_p > 4000: # Abnormally long ON is a gap
            break
            
        if on_p > config["threshold"]:
            bits.append(1)
        else:
            bits.append(0)

    if not bits: return None
    return _bits_to_hex(bits)

def _bits_to_hex(bits: list[int]) -> str:
    """Convert bit list to hex string (LSB First)."""
    hex_str = ""
    # Process bits in 8-bit chunks
    for i in range(0, len(bits), 8):
        chunk = bits[i:i+8]
        byte_val = 0
        for b_idx, b_val in enumerate(chunk):
            if b_val:
                byte_val |= (1 << b_idx)
        hex_str += f"{byte_val:02X}"
    return hex_str
