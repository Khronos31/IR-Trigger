import logging
import asyncio
from abc import ABC, abstractmethod
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import (
    TX_TYPE_USB_AD00020P,
    TX_TYPE_ESPHOME,
    TX_TYPE_WEBHOOK,
    TX_TYPE_NATURE_REMO,
    TX_TYPE_MOCK,
    CONF_TYPE,
    CONF_INDEX,
    CONF_ENTITY_ID,
)

_LOGGER = logging.getLogger(__name__)

class TXInterface(ABC):
    """Base class for IR Transmitters."""
    @abstractmethod
    async def async_send(self, code: str, force_aeha_tx: bool = False):
        pass

class USBad00020pTX(TXInterface):
    def __init__(self, hass, index: int = 0):
        self.hass = hass
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
                self._dev.get_active_configuration()
                return self._dev
            except:
                self._dev = None
        devs = list(usb.core.find(find_all=True, idVendor=self._vid, idProduct=self._pid))
        if not devs or len(devs) <= self.index:
            return None
        dev = devs[self.index]
        try:
            try: dev.set_configuration()
            except: pass
            try:
                if dev.is_kernel_driver_active(self._interface):
                    dev.detach_kernel_driver(self._interface)
            except: pass
            usb.util.claim_interface(dev, self._interface)
            self._dev = dev
            return dev
        except:
            return None

    async def async_send(self, code: str, force_aeha_tx: bool = False):
        if force_aeha_tx and code.startswith("NEC_"):
            code = code.replace("NEC_", "AEHA_", 1)
        parts = code.split('_')
        if len(parts) != 2: return
        fmt_str, hex_code = parts
        fmt_map = {"AEHA": 1, "NEC": 2, "SONY": 3}
        fmt_type = fmt_map.get(fmt_str.upper(), 1)
        try:
            byte_data = bytes.fromhex(hex_code)
        except: return
        bit_len = len(byte_data) * 8
        packet = bytearray(64)
        packet[0], packet[1], packet[2], packet[3] = 0x61, fmt_type, bit_len & 0xFF, (bit_len >> 8) & 0xFF
        packet[4:4+len(byte_data)] = byte_data
        
        _LOGGER.info("Initiating USB IR transmission: %s (index: %d, force_aeha: %s)", code, self.index, force_aeha_tx)
        async with self._lock:
            await asyncio.to_thread(self._do_send, packet)

    def _do_send(self, packet):
        dev = self._open_device()
        if dev:
            try:
                dev.write(self._endpoint_out, packet, timeout=1000)
            except Exception as e:
                _LOGGER.error("Failed to send USB IR code on index %d: %s", self.index, e)
                if self._dev:
                    import usb.util
                    usb.util.dispose_resources(self._dev)
                self._dev = None
        else:
            _LOGGER.error("USB device not found or failed to open for index %d", self.index)

class ESPHomeTX(TXInterface):
    def __init__(self, hass, entity_id):
        self.hass = hass
        self.entity_id = entity_id

    async def async_send(self, code: str, force_aeha_tx: bool = False):
        from . import converter
        raw = converter.code_to_raw(code)
        if not raw:
            _LOGGER.error("Failed to convert code to RAW for ESPHome: %s", code)
            return

        # ESPHome remote.send_command expects [ON, -OFF, ON, -OFF...]
        # we convert our internal [ON, OFF, ON, OFF...] array
        esphome_raw = []
        for i, pulse in enumerate(raw):
            if i % 2 == 1: # Odd index is OFF time
                esphome_raw.append(-abs(pulse))
            else: # Even index is ON time
                esphome_raw.append(abs(pulse))

        _LOGGER.info("Sending ESPHome Native RAW TX: %s via %s", code, self.entity_id)
        try:
            await self.hass.services.async_call("remote", "send_command", {
                "entity_id": self.entity_id,
                "command": esphome_raw
            }, blocking=True)
            _LOGGER.info("ESPHome Native TX sent successfully")
        except Exception as e:
            _LOGGER.error("Error sending ESPHome Native TX to %s: %s", self.entity_id, e)

class WebhookTX(TXInterface):
    def __init__(self, hass, url):
        self.hass = hass
        self.url = url
        
    async def async_send(self, code: str, force_aeha_tx: bool = False):
        from . import converter
        raw = converter.code_to_raw(code)
        if not raw:
            _LOGGER.error("Failed to convert code to RAW: %s", code)
            return

        _LOGGER.info("Sending Webhook TX (RAW): %s -> %s", code, self.url)
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(10):
                # Send as raw pulse array for V2 "Dumb Pipe" architecture
                await session.post(self.url, json={"raw": raw})
            _LOGGER.info("Webhook TX sent successfully")
        except Exception as e:
            _LOGGER.error("Error sending Webhook TX to %s: %s", self.url, e)

class NatureRemoTX(TXInterface):
    def __init__(self, hass, ip):
        self.hass = hass
        if not ip:
            _LOGGER.error("NatureRemoTX initialized without IP address")
        self.url = f"http://{ip}/messages"

    async def async_send(self, code: str, force_aeha_tx: bool = False):
        from . import converter
        raw = converter.code_to_raw(code)
        if not raw:
            _LOGGER.error("Failed to convert code to RAW for Nature Remo: %s", code)
            return

        _LOGGER.info("Sending Nature Remo Local TX (RAW): %s -> %s", code, self.url)
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(10):
                headers = {"X-Requested-With": "local"}
                # Nature Remo Local API format: us pulses, 38kHz
                payload = {"format": "us", "freq": 38, "data": raw}
                await session.post(self.url, json=payload, headers=headers)
            _LOGGER.info("Nature Remo Local TX sent successfully")
        except Exception as e:
            _LOGGER.error("Error sending Nature Remo TX to %s: %s", self.url, e)

class MockTX(TXInterface):
    async def async_send(self, code: str, force_aeha_tx: bool = False):
        _LOGGER.info("[MOCK] Sending: %s", code)

def create_transmitter(hass: HomeAssistant, config: dict) -> TXInterface:
    tx_type = config.get(CONF_TYPE)
    if tx_type == TX_TYPE_USB_AD00020P:
        return USBad00020pTX(hass, config.get(CONF_INDEX, 0))
    elif tx_type == TX_TYPE_ESPHOME:
        return ESPHomeTX(hass, config.get(CONF_ENTITY_ID))
    elif tx_type == TX_TYPE_WEBHOOK:
        return WebhookTX(hass, config.get("url"))
    elif tx_type == TX_TYPE_NATURE_REMO:
        return NatureRemoTX(hass, config.get("ip"))
    elif tx_type == TX_TYPE_MOCK:
        return MockTX()
    return MockTX() # Default fallback
