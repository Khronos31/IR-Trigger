import logging
import asyncio
from abc import ABC, abstractmethod
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import base64
from .const import (
    TX_TYPE_ESPHOME,
    TX_TYPE_WEBHOOK,
    TX_TYPE_NATURE_REMO,
    TX_TYPE_BROADLINK,
    TX_TYPE_MOCK,
    CONF_TYPE,
    CONF_INDEX,
    CONF_ENTITY_ID,
    CONF_NODE_NAME,
)

_LOGGER = logging.getLogger(__name__)

class TXInterface(ABC):
    """Base class for IR Transmitters."""
    @abstractmethod
    async def async_send(self, code: str):
        pass

class ESPHomeTX(TXInterface):
    def __init__(self, hass, node_name):
        self.hass = hass
        self.node_name = node_name

    async def async_send(self, code: str):
        from . import converter
        raw = converter.code_to_raw(code)
        if not raw:
            _LOGGER.error("Failed to convert code to RAW for ESPHome: %s", code)
            return

        # ESPHome command expects [ON, -OFF, ON, -OFF...]
        esphome_raw = []
        for i, pulse in enumerate(raw):
            if i % 2 == 1: # Odd index is OFF time
                esphome_raw.append(-abs(pulse))
            else: # Even index is ON time
                esphome_raw.append(abs(pulse))

        # Call custom ESPHome action: esphome.<node_name>_send_raw
        service_name = f"{self.node_name}_send_raw"

        _LOGGER.info("Sending ESPHome Custom RAW TX: %s via esphome.%s", code, service_name)
        try:
            await self.hass.services.async_call("esphome", service_name, {
                "command": esphome_raw
            }, blocking=True)
            _LOGGER.info("ESPHome Custom TX sent successfully")
        except Exception as e:
            _LOGGER.error("Error sending ESPHome Custom TX to %s: %s", service_name, e)

class WebhookTX(TXInterface):
    def __init__(self, hass, url):
        self.hass = hass
        self.url = url
        
    async def async_send(self, code: str):
        from . import converter
        raw = converter.code_to_raw(code)
        if not raw:
            _LOGGER.error("Failed to convert code to RAW: %s", code)
            return

        _LOGGER.info("Sending Webhook TX (RAW): %s -> %s", code, self.url)
        session = async_get_clientsession(self.hass)
        try:
            async with asyncio.timeout(10):
                # Send as raw pulse array for "Dumb Pipe" architecture with code string for display
                await session.post(self.url, json={"code": code, "raw": raw})
            _LOGGER.info("Webhook TX sent successfully")
        except Exception as e:
            _LOGGER.error("Error sending Webhook TX to %s: %s", self.url, e)

class NatureRemoTX(TXInterface):
    def __init__(self, hass, ip):
        self.hass = hass
        if not ip:
            _LOGGER.error("NatureRemoTX initialized without IP address")
        self.url = f"http://{ip}/messages"

    async def async_send(self, code: str):
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

class BroadlinkTX(TXInterface):
    def __init__(self, hass, entity_id):
        self.hass = hass
        if not entity_id:
            _LOGGER.error("BroadlinkTX initialized without entity_id")
        self.entity_id = entity_id

    async def async_send(self, code: str):
        from . import converter
        raw = converter.code_to_raw(code)
        if not raw:
            _LOGGER.error("Failed to convert code to RAW for Broadlink: %s", code)
            return

        # Convert to Broadlink packet (Base64)
        packet = bytearray([0x26, 0x00]) # 0x26 = IR, 0x00 = repeat 0 times
        payload = bytearray()
        
        # Broadlink tick calculation: ~32.84us per tick (269/8192 * 1000)
        for pulse in raw:
            val = int(round(pulse * 269.0 / 8192.0))
            if val == 0: val = 1
            if val <= 255:
                payload.append(val)
            else:
                payload.append(0x00)
                payload.append((val >> 8) & 0xFF) # Big-Endian
                payload.append(val & 0xFF)
                
        # Trailing gap to signal end of transmission (0x0D 0x05 -> ~109ms)
        payload.extend([0x00, 0x0D, 0x05])
        
        # Length header
        packet.append(len(payload) & 0xFF)
        packet.append((len(payload) >> 8) & 0xFF)
        packet.extend(payload)
        
        b64_code = base64.b64encode(packet).decode('utf-8')
        b64_code_prefixed = f"b64:{b64_code}"

        _LOGGER.info("Sending Broadlink TX: %s via remote.send_command", code)
        try:
            await self.hass.services.async_call(
                "remote", 
                "send_command", 
                {
                    "entity_id": self.entity_id,
                    "command": [b64_code_prefixed]
                }, 
                blocking=False
            )
            _LOGGER.info("Broadlink TX sent successfully")
        except Exception as e:
            _LOGGER.error("Error sending Broadlink TX to %s: %s", self.entity_id, e)

class MockTX(TXInterface):
    async def async_send(self, code: str):
        _LOGGER.info("[MOCK] Sending: %s", code)

def create_transmitter(hass: HomeAssistant, config: dict) -> TXInterface:
    tx_type = config.get(CONF_TYPE)
    if tx_type == TX_TYPE_ESPHOME:
        return ESPHomeTX(hass, config.get(CONF_NODE_NAME))
    elif tx_type == TX_TYPE_WEBHOOK:
        return WebhookTX(hass, config.get("url"))
    elif tx_type == TX_TYPE_NATURE_REMO:
        return NatureRemoTX(hass, config.get("ip"))
    elif tx_type == TX_TYPE_BROADLINK:
        return BroadlinkTX(hass, config.get(CONF_ENTITY_ID))
    elif tx_type == TX_TYPE_MOCK:
        return MockTX()
    return MockTX() # Default fallback
