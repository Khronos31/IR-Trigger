import logging
import math
import base64

_LOGGER = logging.getLogger(__name__)

# IR Protocol Constants (all values in microseconds)
# Based on AD00020P firmware (main.c) logic where time units are 0.1ms (100us)
# We convert them to us for our internal logic.

TOLERANCE = 0.30 # Increased tolerance for hardware variance

PROTOCOLS = {
    "SWITCHBOT": {
        "leader_on": 8700,
        "leader_off": 4450,
        "bit_on": 670,
        "bit0_off": 715,
        "bit1_off": 2070,
        "threshold": 1400,
        "bit_length": 26,
    },
    "NEC": {
        "leader_on": 9000,
        "leader_off": 4500,
        "bit_on": 560,
        "bit0_off": 560,
        "bit1_off": 1680,
        "threshold": 1200, # If OFF > 1200us, it's bit 1
        "bit_length": 32,
    },
    "AEHA": { # KADEN
        "leader_on": 3200,
        "leader_off": 1600,
        "bit_on": 400,
        "bit0_off": 400,
        "bit1_off": 1200,
        "threshold": 800, # If OFF > 800us, it's bit 1
        "bit_length": 48,
    },
    "SONY": {
        "leader_on": 2400,
        "leader_off": 600,
        "bit_on_0": 600,
        "bit_on_1": 1200,
        "bit_off": 600,
        "threshold": 900, # If ON > 900us, it's bit 1
        "bit_length": 12, # Base length, varies
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
    if code.startswith("B64-"):
        try:
            b64_str = code[4:]
            b = base64.b64decode(b64_str)
            if len(b) < 4:
                return []
            # Skip Broadlink packet header: 0x26 0x00 Length_L Length_H
            payload = b[4:]
            raw = []
            i = 0
            while i < len(payload):
                val = payload[i]
                i += 1
                if val == 0x00 and i + 1 < len(payload):
                    val = (payload[i] << 8) | payload[i+1] # Big-Endian
                    i += 2
                
                # Stop processing if we hit trailing bytes (typically 0x0D 0x05)
                # But we can also just convert them as pulses which will just be long gap at the end
                if i >= len(payload) - 2 and payload[i-1] == 0x0D and payload[i] == 0x05:
                    break

                us = int(round(val * 8192.0 / 269.0))
                raw.append(us)
            return raw
        except Exception as e:
            _LOGGER.error("Failed to decode Broadlink Base64 code: %s", e)
            return []

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

    if name not in PROTOCOLS:
        return []

    config = PROTOCOLS[name]
    
    if len(parts) >= 3:
        bit_length = int(parts[2])
    else:
        # Determine bit length dynamically based on hex string length and protocol default
        hex_bits = len(hex_data) * 4
        
        if "bit_length" in config:
            # Check if the hex string is just padded (e.g. 26bit requires 8 hex chars = 32 bits)
            if hex_bits <= config["bit_length"] + 7:
                bit_length = config["bit_length"]
            else:
                # If the string is significantly longer than the default (like AEHA 88bit), use string length
                bit_length = hex_bits
        else:
            bit_length = hex_bits
            
    # Convert HEX to bits using IRremoteESP8266 logic
    bits = []
    try:
        if name == "NEC":
            val = int(hex_data, 16)
            # IRremoteESP8266's NEC: LSB first globally when sending pulses, 
            # but represented as MSB first in hex where each byte is bit-reversed.
            # We must reconstruct the raw LSB-first pulse stream from this format.
            for i in range(0, bit_length, 8):
                # Extract byte starting from the highest order to match the hex representation
                byte_val = (val >> (bit_length - 8 - i)) & 0xFF
                # Reverse the bits in this byte since IRremoteESP8266 reverses them when building the hex
                rev_byte_val = int(f"{byte_val:08b}"[::-1], 2)
                for j in range(8):
                    bits.append((rev_byte_val >> j) & 1)
        elif name == "SONY":
            val = int(hex_data, 16)
            # SONY: MSB First
            for i in range(bit_length):
                bits.append((val >> (bit_length - 1 - i)) & 1)
        else:
            # DAIKIN, SWITCHBOT, AEHA, etc.: LSB First per byte, hex strings map linearly to bytes
            # Pad hex data to even number of characters to process by bytes
            if len(hex_data) % 2 != 0:
                hex_data = "0" + hex_data
            
            for i in range(0, len(hex_data), 2):
                byte_val = int(hex_data[i:i+2], 16)
                for j in range(8):
                    if len(bits) < bit_length:
                        bits.append((byte_val >> j) & 1)
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
        if name == "SWITCHBOT":
            raw.append(35500) # Broadlink learned gap (~35.5ms)
            raw.append(config["leader_on"])
            raw.append(config["leader_off"] // 2)
            raw.append(config["bit_on"])
        elif name == "NEC":
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
    
    is_default_len = ("bit_length" in config and len(bits) == config["bit_length"])
    
    # Require strict length match for specific protocols like SWITCHBOT
    if protocol_name == "SWITCHBOT" and not is_default_len:
        return None
            
    hex_str = _bits_to_hex(bits, protocol_name)
    
    if not is_default_len and len(bits) % 8 != 0:
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
    
    is_default_len = ("bit_length" in config and len(bits) == config["bit_length"])
    if not is_default_len and len(bits) % 8 != 0:
        return f"{hex_str}-{len(bits)}"
    return hex_str

def _bits_to_hex(bits: list[int], protocol: str) -> str:
    """Convert bit list to hex string using IRremoteESP8266 logic."""
    if protocol == "NEC":
        val = 0
        # NEC: Reconstruct the IRremoteESP8266 32-bit (or custom length) value.
        # It takes LSB-first received bits, but builds an MSB-first value where each byte's bits are reversed.
        for i in range(0, len(bits), 8):
            byte_val = 0
            chunk = bits[i:i+8]
            for j, b in enumerate(chunk):
                if b:
                    byte_val |= (1 << j)
            # Bit reverse the byte_val
            rev_byte_val = int(f"{byte_val:08b}"[::-1], 2)
            val |= (rev_byte_val << (len(bits) - 8 - i))
        digits = max(2, (len(bits) + 3) // 4)
        return f"{val:0{digits}X}"
    elif protocol == "SONY":
        val = 0
        # SONY: MSB First
        for i, b in enumerate(bits):
            if b:
                val |= (1 << (len(bits) - 1 - i))
        digits = max(2, (len(bits) + 3) // 4)
        return f"{val:0{digits}X}"
    else:
        # DAIKIN, SWITCHBOT, AEHA, etc.: LSB First
        # These are long protocols, use byte-wise string concatenation to avoid 64-bit integer limits
        # and match C++ parsing capabilities
        hex_str = ""
        for i in range(0, len(bits), 8):
            byte_val = 0
            chunk = bits[i:i+8]
            for j, b in enumerate(chunk):
                if b:
                    byte_val |= (1 << j)
            hex_str += f"{byte_val:02X}"
        return hex_str
