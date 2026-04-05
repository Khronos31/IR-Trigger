# Transmitter Setup Guide (TX Config)

When you interact with a virtual entity (like a TV or Light) in Home Assistant, IR-Trigger commands your designated edge device (Transmitter) to blast the corresponding IR pulses.

Select the transmission mechanism that fits your setup.

---

## 1. Webhook (Recommended)

Fires a POST request containing a lightweight JSON payload to any listening web server on your microcontroller.
Because HA handles the translation from Protocol/HEX to raw pulse durations, your microcontroller (like **Panopticon**) acts purely as a "Dumb Pipe", taking the array and pushing it straight to its RMT or PWM hardware.

### Configuration (`IR-Trigger.yaml`)
```yaml
transmitters:
  tx_webhook:
    name: "Webhook Transmitter"
    type: webhook
    url: "http://<ESP32_IP>:80/tx"
```

### Network Payload Specs (JSON)
Home Assistant POSTs the following payload structure to your URL:

```json
{
  "code": "NEC-80EA12ED",
  "raw": [9000, 4500, 560, 1680, 560, 560, ...]
}
```

- **`code`**: The Protocol and HEX code string. Use this as metadata to render a beautiful "TX: NEC-80EA12ED" log on your edge device's OLED screen.
- **`raw`**: An array of microsecond (μs) pulse durations. Just feed this directly into `delayMicroseconds` or an RMT peripheral to fire the signal.

---

## 2. ESPHome

Transmits signals natively through the official Home Assistant ESPHome integration.
Under the hood, IR-Trigger dynamically calls a custom ESPHome service named `esphome.<node_name>_send_raw`.

### Configuration (`IR-Trigger.yaml`)
```yaml
transmitters:
  tx_study:
    name: "Study Transmitter"
    type: esphome
    node_name: "atom_s3_study"
```

### ESPHome Configuration (`esphome.yaml`)
Your ESPHome device must expose an `api` service to catch the `send_raw` action.

```yaml
api:
  services:
    - service: send_raw
      variables:
        command: int[]
      then:
        - remote_transmitter.transmit_raw:
            carrier_frequency: 38kHz
            code: !lambda "return command;"
```
*Dive deeper:* Check out `tools/esphome/AtomS3.yaml` for a complete reference implementation.

---

## 3. Nature Remo (Local API)

Blasts IR signals directly by calling your Nature Remo's local API. Zero cloud, zero latency, maximum stability.

### Configuration (`IR-Trigger.yaml`)
```yaml
transmitters:
  tx_living:
    name: "Living Room Transmitter"
    type: nature_remo
    ip: "192.168.1.30"
```
*Note:* Make sure you supply the static local IP address of your Nature Remo.

---

## 4. Broadlink

Sends Base64 encoded commands via the official Home Assistant Broadlink integration using the `remote.send_command` service.

### Configuration (`IR-Trigger.yaml`)
```yaml
transmitters:
  tx_broadlink:
    name: "Living Room Broadlink"
    type: broadlink
    entity_id: remote.broadlink_living_room
```
*Note:* Provide the entity ID of your Broadlink remote. IR-Trigger handles the precise timing conversions from raw pulses to Broadlink's specific tick encoding automatically.

---

## 5. Mock (Test/Debug)

A virtual transmitter that outputs what *would* have been sent directly into the Home Assistant logs.
Perfect for verifying your complex routing, state machines, or dictionaries without actually blasting your real-world appliances.

### Configuration (`IR-Trigger.yaml`)
```yaml
transmitters:
  tx_debug:
    name: "Debug Transmitter"
    type: mock
```

Upon transmission, check your HA logs for a trace like this:
```text
[MOCK] Sending: NEC-80EA12ED