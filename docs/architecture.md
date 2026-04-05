# Architecture (The Grand Unification)

IR-Trigger is designed to be the ultimate central nervous system for your smart home's infrared communication. By embracing the "Dumb Pipe, Smart Core" philosophy, we offload all complex protocol decoding and routing logic to Home Assistant, freeing up your edge devices (microcontrollers) to simply push and pull raw pulses.

---

## 1. Absolute Separation of TX and RX (TX/RX Separation)

IR-Trigger treats the physical "Transmission" (TX) and "Reception" (RX) capabilities as completely independent components. This allows you to mix and match TX-only devices (like ESP32 generic blasters) with RX-only units, or combine them as you see fit.

- **Transmitter (TX)**: The physical hardware emitting the IR pulses. `esphome`, `nature_remo`, `webhook`, `broadlink`, etc.
- **Receiver (RX)**: The physical hardware catching the IR pulses. `webhook`, `nature_remo`, etc.
- **Device (Appliance)**: A virtual entity bound to a specific `transmitter`. These spawn as standard HA entities like buttons, lights, or media players.

This architectural split means your transmitters and receivers are visualized as independent hardware nodes in the HA Device Registry, making your setup much more intuitive to manage.

---

## 2. Webhook-Driven Flow & RESTful Design

When an edge device catches a rogue IR pulse, the pipeline to trigger a Home Assistant action is razor-thin and lightning-fast.

### 2.1. RESTful Signal Detection
1. **Receive**: Your hardware catches a raw pulse array or decoded code (e.g., `NEC-80EA12ED`).
2. **Webhook POST**: It fires a lightweight JSON payload `{"code": "...", "raw": [...]}` to its dedicated endpoint (e.g., `/api/webhook/rx_study_webhook`).
3. **Event Ignition**: HA immediately fires the `ir_trigger_received` event. The Webhook ID automatically identifies the source receiver.

### 2.2. The Logic Engine (Smart Core)
Based on the current state of your `mode_entity` and YAML configs, IR-Trigger executes:

- **Auto-Repeater**:
  - If the incoming code belongs to a device in the `repeat` list, IR-Trigger instantly echoes the exact same signal out through its assigned transmitter.
- **Dynamic Binding**:
  - If a source (remote) and target (appliance) are `bind`ed, IR-Trigger intercepts the source's button press and blasts the corresponding target's code based on the active mode.
- **Remapping**:
  - Hijack any IR code to trigger arbitrary HA services or blast different IR signals.

---

## 3. Built for Reliability and Stability

### 3.1. Infinite Loop Prevention (Howling)
When acting as an IR repeater, there's a risk your receiver catches the very signal your transmitter just blasted, causing an infinite loop.
IR-Trigger nullifies this. By defining a `local_receivers` list on your `Transmitter` config, the system blocks the transmission if the triggering signal was just caught by a receiver sitting right next to it.

### 3.2. Explicit Template Paths (KISS Principle)
Template references enforce full-path clarity like `template: "media_player/J-MX100RC"`. No guessing games, no conflicting filenames. It keeps file lookups instantaneous and your configurations bulletproof.
