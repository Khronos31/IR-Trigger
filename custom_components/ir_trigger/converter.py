import logging
import math

_LOGGER = logging.getLogger(__name__)

# NEC Protocol Constants (microseconds)
NEC_LEADER_ON = 9000
NEC_LEADER_OFF = 4500
NEC_BIT_ON = 560
NEC_LOGIC_0_OFF = 560
NEC_LOGIC_1_OFF = 1690
TOLERANCE = 0.25 # 25% tolerance

def raw_to_code(raw: list[int]) -> str:
    """Convert raw pulse array to a hex string or RAW format."""
    if not raw:
        return ""

    # Attempt NEC decoding
    nec_code = _decode_nec(raw)
    if nec_code:
        return f"NEC_{nec_code}"

    # Fallback to RAW format
    csv_pulses = ",".join(map(str, raw))
    return f"RAW_{csv_pulses}"

def code_to_raw(code: str) -> list[int]:
    """Convert hex string (e.g. NEC_56A9718E) back to raw pulse array."""
    raise NotImplementedError("code_to_raw is not implemented yet")

def _decode_nec(raw: list[int]) -> str | None:
    """Try to decode pulses as NEC protocol. Returns 8-char hex string or None."""
    # NEC requires at least leader (2) + 32 bits (64 pulses) = 66 pulses
    if len(raw) < 66:
        return None

    # Check leader
    if not _is_match(raw[0], NEC_LEADER_ON) or not _is_match(raw[1], NEC_LEADER_OFF):
        return None

    bits = []
    # Start from index 2, skip leader pulse pair
    for i in range(2, 66, 2):
        if i + 1 >= len(raw):
            break
        
        on_p = raw[i]
        off_p = raw[i+1]
        
        if not _is_match(on_p, NEC_BIT_ON):
            return None # Bit sync failed
        
        if _is_match(off_p, NEC_LOGIC_0_OFF):
            bits.append(0)
        elif _is_match(off_p, NEC_LOGIC_1_OFF):
            bits.append(1)
        else:
            return None # Unknown pulse width

    if len(bits) < 32:
        return None

    # NEC is LSB first. Group into 4 bytes (8 bits each)
    byte_vals = []
    for b in range(4):
        byte_val = 0
        for i in range(8):
            if bits[b*8 + i]:
                byte_val |= (1 << i)
        byte_vals.append(byte_val)
    
    return "".join(f"{v:02X}" for v in byte_vals)

def _is_match(actual: int, target: int) -> bool:
    """Check if actual pulse width is within tolerance of target."""
    return target * (1 - TOLERANCE) <= actual <= target * (1 + TOLERANCE)
