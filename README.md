# IR-Trigger

The ultimate lightweight, high-response, bi-directional Infrared (IR) integration system for Home Assistant.
IR-Trigger goes beyond simply receiving IR signals to trigger automations. It empowers you to transmit IR signals from standard Home Assistant entities (Lights, Media Players, etc.) and buttons, providing seamless, direct control of your legacy appliances.

[日本語ドキュメントはこちら (Japanese Documentation)](README-ja.md)

---

## 🚀 Features

1. **Bi-directional IR Communication (Dumb Pipe, Smart Core)**
   - **[Receivers (RX)](docs/receivers.md)**: Instantly normalizes incoming raw signals and reflects them in Home Assistant events and sensors.
   - **[Transmitters (TX)](docs/transmitters.md)**: Emits raw IR pulses via Webhooks, ESPHome, Nature Remo, or Broadlink directly from your HA entities.
2. **Multi-State Machine**
   - Define independent `state_machines` for AV equipment, lighting, and other complex scenarios.
   - Built-in anti-chattering and debounce logic for flawless signal routing.
3. **Auto-Domain Wrapper**
   - Simply define `domain` and `mapping` in your remote dictionary, and IR-Trigger automatically spawns standard Home Assistant entities (like `light` or `media_player`).
4. **Template Ecosystem (The Dictionary)**
   - Define `template: "model"` to effortlessly load built-in or custom user dictionaries.
   - **Native Broadlink Base64 (`B64-`) support**: Copy and paste the massive trove of Broadlink Base64 codes from the internet straight into your dictionaries!
5. **Hub & Spoke Architecture (via_device)**
   - Elegantly links transmitters (Hubs) and appliance devices (Spokes) natively within the Home Assistant Device Registry.

---

## 📦 1. Installation

### Installing the Custom Component
1. Add the custom repository `https://github.com/Khronos31/IR-Trigger` in HACS and download it.
2. Add the following to your `configuration.yaml` and restart Home Assistant:
   ```yaml
   ir_trigger:
   ```

---

## 📝 2. Configuration (IR-Trigger.yaml)

Embrace the KISS principle. Keep your config declarative and clean.

```yaml
# 1. Transmitters (Physical Devices)
transmitters:
  tx_study:
    name: "Study Transmitter"
    type: esphome
    node_name: "atom_s3_study"
    local_receivers: ["rx_study_webhook"] # Infinite loop (howling) prevention

# 2. Receivers (Physical Devices)
receivers:
  rx_study_webhook:
    name: "Study Webhook Receiver"
    type: webhook
  rx_living_esp:
    name: "Living Room ESP Receiver"
    type: webhook # Listens at /api/webhook/rx_living_esp

# 3. Appliance Devices (Virtual Entities)
devices:
  TV_Study:
    name: "Study TV"
    transmitter: tx_study
    template: "media_player/J-MX100RC" # Explicit category path

# 4. Global Configuration
global:
  repeat: ["TV_Study"] # Auto-repeater
  remap:
    "NEC-12345678": # Call HA services on specific button presses
      - service: light.toggle
        target: { entity_id: light.living }

# 5. State Machines (Dynamic Routing based on Mode)
state_machines:
  - name: "Study AV"
    mode_entity: input_select.ir_remote_mode
    modes:
      TV:
        bind:
          - { source: Master_Remote, target: TV_Study }
```

---

## 📖 3. Dictionary Files (Templates)

You can place shared remote definitions in the following directories. Specify the relative path (excluding `.yaml`) in your config.

- **Built-in Dictionaries:** `custom_components/ir_trigger/remotes/`
- **Custom User Dictionaries:** `config/ir_trigger_remotes/`

📚 Check out the list of supported remotes (built-in):  
https://github.com/Khronos31/IR-Trigger/tree/main/custom_components/ir_trigger/remotes  

### Leveraging Broadlink Base64 Assets
Found a massive database of air conditioner codes in Broadlink Base64 format (e.g., `JgBQAAAB...`) on the internet? Just paste them into your dictionary file!
Simply prepend `B64-` to the code, and IR-Trigger will automatically decode and translate it into the universal raw pulse format for HA, ESPHome, Nature Remo, or Webhooks.

Have a JSON file full of Base64 codes? Use the included tool to blast it into a YAML dictionary in seconds:
```bash
python3 tools/scripts/broadlink_json_to_yaml.py input.json output.yaml --domain climate
```

---

## 🛠️ 4. Troubleshooting

No known limitations at this time. Enjoy the Local Push freedom!
