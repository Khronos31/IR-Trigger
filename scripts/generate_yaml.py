import os
import re
import math

CONFIG_DIR = "lua-remote-hub/ha-addon/config"
OUTPUT_FILE = "IR-Trigger.yaml"

def parse_signal(signal_str):
    parts = signal_str.strip().split(':')
    if len(parts) < 3:
        return None
    
    try:
        format_id = int(parts[0], 16)
        len1 = int(parts[1], 16)
        len2 = int(parts[2], 16)
    except ValueError:
        return None
        
    total_bits = len1 + len2
    valid_bytes = math.ceil(total_bits / 8)
    
    payload_parts = parts[3 : 3 + valid_bytes]
    hex_payload = "".join(payload_parts).upper()
    
    if format_id == 1:
        prefix = "AEHA_"
    elif format_id == 2:
        prefix = "NEC_"
    elif format_id == 3:
        prefix = "SONY_"
    elif format_id == 4:
        prefix = "MITSUBISHI_"
    elif format_id in (5, 6):
        prefix = "DAIKIN_"
    else:
        prefix = "RAW_"
        
    return f"{prefix}{hex_payload}"

result_dict = {}

for filename in os.listdir(CONFIG_DIR):
    if not filename.endswith(".lua"):
        continue
        
    controller_name = os.path.splitext(filename)[0]
    filepath = os.path.join(CONFIG_DIR, filename)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Check if type is IR
    if not re.search(r'BUTTONS\.type\s*=\s*"IR"', content):
        continue
        
    # Extract keys block
    keys_match = re.search(r'BUTTONS\.keys\s*=\s*\{([^}]+)\}', content)
    if not keys_match:
        continue
        
    keys_block = keys_match.group(1)
    
    # Extract each key-value
    # format: KEY = "02:20:00:50:af:17:e8"
    pattern = r'([A-Za-z0-9_]+)\s*=\s*"([0-9a-fA-F:]+)"'
    for match in re.finditer(pattern, keys_block):
        button_name = match.group(1)
        raw_signal = match.group(2)
        
        normalized_signal = parse_signal(raw_signal)
        if normalized_signal:
            result_dict[normalized_signal] = {
                "controller": controller_name,
                "button": button_name
            }

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write("# IR-Trigger.yaml - Generated from lua-remote-hub\n\n")
    for signal in sorted(result_dict.keys()):
        data = result_dict[signal]
        f.write(f'"{signal}":\n')
        f.write(f'  controller: "{data["controller"]}"\n')
        f.write(f'  button: "{data["button"]}"\n\n')

print(f"Generated {OUTPUT_FILE} with {len(result_dict)} IR signals.")
