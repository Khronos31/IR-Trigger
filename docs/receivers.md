# Receiver Setup Guide (RX Config)

IR-Trigger utilizes edge devices (Receivers) to capture signals and seamlessly feed them to Home Assistant. Choose the setup that best suits your hardware.

---

## 1. Webhook via Dumb Pipe (Highly Recommended)

The purest, fastest approach. Have your microcontroller, Linux daemon, or ESP32 blast Webhooks directly into the HA pipeline.

### Webhook Endpoint
`http://<HA_IP>:8123/api/webhook/<receiver_id>`
*Note:* `<receiver_id>` corresponds directly to the key you define in your `receivers:` block of `IR-Trigger.yaml`.

### Payload Format (JSON)
The Webhook accepts two types of payloads depending on where your processing power lies.

**Pattern 1: Decoded Code String**
```json
{
  "code": "NEC-80EA12ED"
}
```
- `code`: `Protocol-HEX` string. Use this if your edge device has the brains to decode the signal before sending.

**Pattern 2: Raw Pulse Array (Dumb Pipe Mode)**
```json
{
  "raw": [9000, 4500, 560, 1680, 560, 560]
}
```
- `raw`: An array of ON/OFF pulse durations in microseconds (all positive integers). Home Assistant acts as the "Smart Core," instantly parsing and decoding the array into Protocol/HEX code under the hood. 
We strongly recommend this "Dumb Pipe" pattern to minimize the processing load on your microcontrollers.

---

## 2. ESPHome / Panopticon (M5Stick / M5Atom, etc.)

For those running ESPHome, use the `http_request` component to fire signals directly into HA.
IR-Trigger also supports **Panopticon**, a specialized, high-performance C++ firmware tailored for flawless, native transmission and reception on ESP32-S3 devices.

### Example configuration (`esphome.yaml`)
```yaml
http_request:
  timeout: 5s

remote_receiver:
  pin: 
    number: GPIO33
    inverted: true
  dump: all
  on_raw:
    then:
      - if:
          condition:
            lambda: 'return x.size() > 20;'
          then:
            - http_request.post:
                url: "http://<HA_IP>:8123/api/webhook/rx_living_esp"
                request_headers:
                  Content-Type: application/json
                body: !lambda |-
                  // Construct raw JSON array from pulses. OFF times are normalized to positive integers for HA processing.
                  std::string payload = "{\"raw\":[";
                  for (size_t i = 0; i < x.size(); i++) {
                    payload += std::to_string(std::abs(x[i]));
                    if (i < x.size() - 1) payload += ", ";
                  }
                  payload += "]}";
                  return payload;
```
*Dive deeper:* Check out `tools/esphome/AtomS3.yaml` for a complete reference implementation.

---

## 3. Nature Remo (Local API)

For users who want zero-cloud dependency with incredible speed and stability. IR-Trigger can scrape signals directly from your Nature Remo device's local API.

### Setup
Ensure you configure the `type: nature_remo` receiver in your `IR-Trigger.yaml` with the correct `ip` address of your Remo unit.
IR-Trigger will automatically poll the `/messages` endpoint locally, bypassing the cloud entirely to deliver near-instantaneous triggers.
