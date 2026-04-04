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
    "NEC-L": {
        "leader_on": 9000,
        "leader_off": 4500,
        "bit_on": 680,
        "bit0_off": 730,
        "bit1_off": 2150,
        "threshold": 1400,
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
            code = _decode_sony(raw, config, name)
        else:
            code = _decode_mark_space(raw, config, name)
        
        if code:
            return f"{name}-{code}"

    # Fallback to RAW format
    csv_pulses = ",".join(map(str, raw))
    return f"RAW-{csv_pulses}"

def code_to_raw(code: str) -> list[int]:
    """Convert code string back to RAW pulse array."""
    if code.startswith("RAW-"):
        try:
            return [int(x) for x in code[4:].split(",")]
        except ValueError:
            return []

    # Format check (e.g., NEC-XXXXXXXX or NEC-XXXXXXXX-26)
    parts = code.split("-")
    if len(parts) < 2:
        return []

    name, hex_data = parts[0], parts[1]
    bit_length = int(parts[2]) if len(parts) >= 3 else len(hex_data) * 4

    if name not in PROTOCOLS:
        return []

    config = PROTOCOLS[name]
    
    # Convert HEX to bits using IRremoteESP8266 logic
    bits = []
    try:
        val = int(hex_data, 16)
        is_msb_first = (name == "SONY")
        
        for i in range(bit_length):
            if is_msb_first:
                # MSB First
                bits.append((val >> (bit_length - 1 - i)) & 1)
            else:
                # LSB First
                bits.append((val >> i) & 1)
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
        
        # 🛡️ NEC系特有のリピートコード付与
        if name in ["NEC", "NEC-L"]:
            raw.append(40000) # 40ms Gap
            raw.append(config["leader_on"])
            raw.append(config["leader_off"] // 2)
            raw.append(config["bit_on"])

    return raw

def _is_match(actual: int, target: int) -> bool:
    """Check if actual pulse width is within tolerance of target."""
    return target * (1 - TOLERANCE) <= actual <= target * (1 + TOLERANCE)

def _decode_mark_space(raw: list[int], config: dict, protocol_name: str) -> str | None:
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
    hex_str = _bits_to_hex(bits, protocol_name)
    if len(bits) % 8 != 0:
        return f"{hex_str}-{len(bits)}"
    return hex_str

def _decode_sony(raw: list[int], config: dict, protocol_name: str) -> str | None:
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
    hex_str = _bits_to_hex(bits, protocol_name)
    if len(bits) % 8 != 0:
        return f"{hex_str}-{len(bits)}"
    return hex_str

def _bits_to_hex(bits: list[int], protocol: str) -> str:
    """Convert bit list to hex string using IRremoteESP8266 logic."""
    val = 0
    # SONY is MSB first, others are LSB first
    is_msb_first = (protocol == "SONY")
    
    for i, b in enumerate(bits):
        if b:
            if is_msb_first:
                # MSB First: first bit is the most significant
                val |= (1 << (len(bits) - 1 - i))
            else:
                # LSB First: first bit is the least significant
                val |= (1 << i)
                
    # Calculate required hex digits (4 bits per hex digit)
    # Minimum 2 digits
    digits = max(2, (len(bits) + 3) // 4)
    # Ensure it's formatted to the correct width
    return f"{val:0{digits}X}"
