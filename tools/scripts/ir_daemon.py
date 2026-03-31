import json
import math
import requests
import time
import sys
import usb.core
import usb.util

VENDOR_ID = 0x22ea
PRODUCT_ID = 0x001e
INTERFACE_NUM = 3
ENDPOINT_OUT = 0x04
ENDPOINT_IN = 0x84
PKT_SIZE = 64

def normalize_ir_data(data) -> str:
    """
    Normalize the 63-byte IR array to a string like 'NEC_56A9718E'.
    
    data: byte array from AD00020P (without the command byte)
    data[0]: Format ID
    data[1]: bit length 1
    data[2]: bit length 2
    data[3:]: payload
    """
    if len(data) < 3:
        return "RAW_UNKNOWN"

    format_id = data[0]
    total_bits = data[1] + data[2]
    valid_bytes = math.ceil(total_bits / 8)

    if len(data) < 3 + valid_bytes:
        payload = data[3:]
    else:
        payload = data[3 : 3 + valid_bytes]

    hex_payload = "".join(f"{b:02X}" for b in payload)

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

def send_to_homeassistant(ha_url: str, code: str):
    """
    Send the normalized code to the Home Assistant Webhook.
    """
    payload = {
        "code": code
    }
    try:
        response = requests.post(ha_url, json=payload, timeout=5)
        response.raise_for_status()
        print(f"Successfully sent {code} to HA.")
    except Exception as e:
        print(f"Error sending data to HA: {e}")

def open_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        print("Bit Trade One AD00020P USB IR Device not found.")
        return None
    
    if dev.is_kernel_driver_active(INTERFACE_NUM):
        try:
            dev.detach_kernel_driver(INTERFACE_NUM)
        except usb.core.USBError as e:
            print(f"Could not detach kernel driver: {e}")
            return None
            
    try:
        usb.util.claim_interface(dev, INTERFACE_NUM)
    except usb.core.USBError as e:
        print(f"Could not claim interface: {e}")
        return None
        
    return dev

def enter_receive_mode(dev):
    """Enter RECEIVE_WAIT_MODE_WAIT (0x53, 0x01)"""
    out_buf = bytearray([0xFF] * PKT_SIZE)
    out_buf[0] = 0x53
    out_buf[1] = 0x01
    try:
        dev.write(ENDPOINT_OUT, out_buf, timeout=1000)
        in_buf = dev.read(ENDPOINT_IN, PKT_SIZE, timeout=1000)
        return in_buf[0] == 0x53
    except usb.core.USBError:
        return False

def pull_ir_data(dev):
    """Poll for IR data using 0x52 command"""
    out_buf = bytearray([0xFF] * PKT_SIZE)
    out_buf[0] = 0x52
    try:
        dev.write(ENDPOINT_OUT, out_buf, timeout=1000)
        in_buf = dev.read(ENDPOINT_IN, PKT_SIZE, timeout=1000)
        if in_buf[0] == 0x52 and in_buf[1] != 0:
            return in_buf[1:]
    except usb.core.USBError:
        pass
    return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Linux daemon for AD00020P IR Receiver")
    parser.add_argument("--url", required=True, help="HA Webhook URL (e.g. http://<HA_IP>:8123/api/webhook/rx_study_usb)")
    args = parser.parse_args()

    print("Starting IR Daemon...")
    dev = open_device()
    if not dev:
        sys.exit(1)
        
    if not enter_receive_mode(dev):
        print("Failed to enter receive mode.")
        sys.exit(1)

    print("Device initialized. Waiting for IR signals...")
    try:
        while True:
            data = pull_ir_data(dev)
            if data:
                code = normalize_ir_data(data)
                print(f"Received raw data -> Normalized: {code}")
                send_to_homeassistant(args.url, code)
                # Reset buffer after receiving
                enter_receive_mode(dev)
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nExiting...")
        # Exit receive mode (0x53, 0x00)
        out_buf = bytearray([0xFF] * PKT_SIZE)
        out_buf[0], out_buf[1] = 0x53, 0x00
        try:
            dev.write(ENDPOINT_OUT, out_buf, timeout=1000)
        except:
            pass
        usb.util.dispose_resources(dev)
