import logging
import asyncio
from abc import ABC, abstractmethod
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class IRTransmitter(ABC):
    """Base class for IR Transmitters."""
    
    @abstractmethod
    async def async_send(self, code: str):
        """Send an IR code."""
        pass

class LocalUSBTransmitter(IRTransmitter):
    """Transmitter using pyusb for local USB devices."""
    
    def __init__(self, index: int = 0):
        self.index = index
        self._dev = None
        self._vid = 0x22ea
        self._pid = 0x001e
        self._interface = 3
        self._endpoint_out = 0x04
        self._lock = asyncio.Lock()

    def _open_device(self):
        import usb.core
        import usb.util
        
        if self._dev:
            try:
                # Test connectivity
                self._dev.get_active_configuration()
                return self._dev
            except:
                self._dev = None
        
        # Determine devices
        devs = list(usb.core.find(find_all=True, idVendor=self._vid, idProduct=self._pid))
        if not devs:
            _LOGGER.error("No USB IR Transmitter found (VID: 0x%04x, PID: 0x%04x)", self._vid, self._pid)
            return None
            
        if len(devs) <= self.index:
            _LOGGER.error("USB IR Transmitter index %s is out of range (found %s devices)", self.index, len(devs))
            # Fallback to first device if index 1 was used by mistake
            if self.index > 0:
                _LOGGER.warning("Falling back to index 0")
                dev = devs[0]
            else:
                return None
        else:
            dev = devs[self.index]
        
        try:
            # Set configuration
            try:
                dev.set_configuration()
            except usb.core.USBError as e:
                if e.errno == 16: # Resource busy
                    _LOGGER.debug("Device already configured or busy: %s", e)
                else:
                    raise
            
            # Detach kernel driver (Linux specific, but handled safely)
            try:
                if dev.is_kernel_driver_active(self._interface):
                    dev.detach_kernel_driver(self._interface)
            except (usb.core.USBError, NotImplementedError):
                pass
            
            # Claim interface
            try:
                usb.util.claim_interface(dev, self._interface)
            except usb.core.USBError as e:
                _LOGGER.error("Could not claim interface %s: %s. Is another process using the device?", self._interface, e)
                return None
            
            self._dev = dev
            _LOGGER.info("Successfully initialized USB IR Transmitter (index %s)", self.index)
            
        except Exception as e:
            _LOGGER.error("Failed to open USB device: %s", e)
            return None
            
        return self._dev

    async def async_send(self, code: str):
        """Send IR code using pyusb."""
        # Split code (e.g., "NEC_56A912ED") into format and bytes
        parts = code.split('_')
        if len(parts) != 2:
            _LOGGER.error("Invalid IR code format for USB: %s", code)
            return

        fmt_str, hex_code = parts
        # Map format string to type byte (based on C++ usbir.h if applicable, 
        # but let's assume 0x01 for NEC as a placeholder or determine from context)
        # Based on BitTradeOne docs, 1: AEHA, 2: NEC, 3: SONY
        fmt_map = {"AEHA": 1, "NEC": 2, "SONY": 3, "MITSUBISHI": 4, "DAIKIN": 5, "DAIKIN2": 6}
        fmt_type = fmt_map.get(fmt_str.upper(), 1)
        
        try:
            byte_data = bytes.fromhex(hex_code)
        except ValueError:
            _LOGGER.error("Invalid hex code: %s", hex_code)
            return

        # Prepare packet (0x61, fmt, len1, len2, data...)
        # len1/len2 logic from C++:
        # int code_len_check = (int)((code_len1 + code_len2) / 8);
        # bit length is usually len(byte_data) * 8
        bit_len = len(byte_data) * 8
        len1 = bit_len & 0xFF
        len2 = (bit_len >> 8) & 0xFF
        
        packet = bytearray(64)
        packet[0] = 0x61
        packet[1] = fmt_type
        packet[2] = len1
        packet[3] = len2
        packet[4:4+len(byte_data)] = byte_data
        
        def _send():
            import usb.core
            dev = self._open_device()
            if dev:
                try:
                    dev.write(self._endpoint_out, packet, timeout=1000)
                    _LOGGER.info("Successfully sent IR code %s via USB", code)
                except Exception as e:
                    _LOGGER.error("Error sending IR via USB: %s", e)
                    # Reset connection on error
                    self._dev = None

        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(None, _send)

class ESPHomeTransmitter(IRTransmitter):
    """Transmitter using ESPHome remote entity."""
    
    def __init__(self, hass: HomeAssistant, entity_id: str):
        self.hass = hass
        self.entity_id = entity_id

    async def async_send(self, code: str):
        """Send IR code via HA service call."""
        # Split code (e.g., "NEC_56A912ED")
        parts = code.split('_')
        if len(parts) != 2:
            _LOGGER.error("Invalid IR code format for ESPHome: %s", code)
            return
            
        protocol, signal = parts
        
        _LOGGER.info("Sending IR code %s via ESPHome %s", code, self.entity_id)
        await self.hass.services.async_call(
            "remote",
            "send_command",
            {
                "entity_id": self.entity_id,
                "command": f"protocol: {protocol}, data: 0x{signal}"
            },
            blocking=True
        )

class WebhookTransmitter(IRTransmitter):
    """Transmitter using Webhook (POST request)."""
    
    def __init__(self, url: str):
        self.url = url
        import aiohttp
        self._session = None

    async def _get_session(self):
        import aiohttp
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def async_send(self, code: str):
        """Send IR code via Webhook."""
        session = await self._get_session()
        _LOGGER.info("Sending IR code %s via Webhook to %s", code, self.url)
        try:
            async with session.post(self.url, json={"code": code}, timeout=10) as response:
                if response.status >= 400:
                    _LOGGER.error("Webhook transmitter failed with status %s", response.status)
        except Exception as e:
            _LOGGER.error("Error sending Webhook IR: %s", e)

class MockTransmitter(IRTransmitter):
    """Mock transmitter for development."""
    async def async_send(self, code: str):
        _LOGGER.info("[MOCK] Sending IR code: %s", code)
