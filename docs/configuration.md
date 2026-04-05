# Configuration Guide (The Matrix)

Master your `IR-Trigger.yaml` to orchestrate transmitters, receivers, state machines, and advanced settings.

---

## 1. The Global Structure

```yaml
transmitters: ...    # 1. Physical blasters (TX)
receivers: ...       # 2. Physical sniffers (RX)
devices: ...         # 3. Virtual appliances (Spokes)
global: ...          # 4. Global rules (Always active repeats/remaps)
state_machines: ...  # 5. Dynamic routing based on modes
```

---

## 2. Physical Device Nodes

### Transmitters (`transmitters`)
Target devices to emit IR blasts from HA.
- `type`: `esphome`, `nature_remo`, `webhook`, `broadlink`, `mock`
- `local_receivers`: A list of nearby receiver IDs to block howling (infinite loops).

### Receivers (`receivers`)
Sensors catching IR signals.
- `type`: `webhook`, `nature_remo`
- If using `webhook`, the receiver ID doubles as the webhook endpoint, listening at `/api/webhook/<receiver_id>`.

---

## 3. Appliance Devices (`devices`)

Spawn your home appliances as native Home Assistant entities.
- `transmitter`: The ID in your `transmitters` block that will blast this device's codes.
- `template`: The path to the remote's dictionary file.
  - **CRITICAL**: Use the full category directory path (e.g., `media_player/J-MX100RC`). Exclude the `.yaml` extension.

### Dictionary File Formats
Map button names to IR codes in your template files. We natively support the following formats:

1. **IRremoteESP8266 Hex Codes** (Recommended)
   - Format: `Protocol-HEXString`
   - Example: `NEC-FF00FF86`

2. **Broadlink Base64 Format** (`B64-` Prefix)
   - Format: `B64-Base64String`
   - Example: `B64-JgBGAJKVDg4ODg4O...`
   - Just copy and paste codes from the massive Broadlink databases floating around the web.

> **💡 Pro Tip:** Sitting on a giant JSON file of Base64 aircon codes? Nuke it into a clean YAML dictionary with our built-in converter script:
> `python3 tools/scripts/broadlink_json_to_yaml.py aircon_codes.json aircon.yaml --domain climate`

---

## 4. Routing & State Machines

### Global Rules (`global`)
- `repeat`: A list of device IDs that will automatically re-transmit any code they receive.
- `remap`: Global actions for specific codes. If matched, **it halts all further evaluation (including state machines)**.

### State Machines (`state_machines`)
Construct independent logic engines for dynamic behavior.
- `mode_entity`: The HA entity defining the current state (e.g., `input_select.av_mode`).
- `modes`: Remap and bind definitions unique to each mode.

---

## 5. Evaluation Order & Execution Lock

When a signal is caught, it flows through the engine like this:
1.  **Repeat**: Checks the `global.repeat` list. If it matches, the assigned transmitter fires it back out.
2.  **Global Remap**: Executes if matched, and **kills the execution flow right here.**
3.  **State Machines**: Evaluates each state machine sequentially. Once a match is found in a machine, it fires and moves to the next machine, preventing overlapping commands within the same engine.

---

## 6. Hot Reloading
Tweak your YAML? Just smash the `ir_trigger.reload` service from the Developer Tools. Instant updates, zero restarts.
