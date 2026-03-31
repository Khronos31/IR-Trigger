import logging
import asyncio
import os
import json
from abc import ABC, abstractmethod
from typing import Optional, Callable
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.webhook import async_register as webhook_register, async_unregister as webhook_unregister
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta

from .const import (
    DOMAIN,
    EVENT_IR_RECEIVED,
    ATTR_RECEIVER,
    ATTR_CODE,
    CONF_TYPE,
    CONF_INDEX,
    CONF_ENTITY_ID,
    CONF_WEBHOOK_ID,
    CONF_POLL_INTERVAL,
    HUB_TYPE_LOCAL_USB,
    HUB_TYPE_ESPHOME,
    HUB_TYPE_WEBHOOK,
    HUB_TYPE_NATURE_REMO,
    HUB_TYPE_MOCK,
)

_LOGGER = logging.getLogger(__name__)

class TXInterface(ABC):
    """Base class for IR Transmitters."""
    @abstractmethod
    async def async_send(self, code: str, force_aeha_tx: bool = False):
        pass

class RXInterface(ABC):
    """Base class for IR Receivers."""
    def __init__(self, hub_id: str, callback_fn: Callable[[str], None]):
        self.hub_id = hub_id
        self.callback_fn = callback_fn

    @abstractmethod
    async def async_setup(self, hass: HomeAssistant):
        pass

    @abstractmethod
    async def async_teardown(self, hass: HomeAssistant):
        pass

class IRHub:
    """Hub class managing TX and RX interfaces."""
    def __init__(self, hass: HomeAssistant, hub_id: str, config: dict):
        self.hass = hass
        self.hub_id = hub_id
        self.name = config.get("name", hub_id)
        
        tx_config = config.get("tx", {})
        rx_config = config.get("rx", {})
        
        self.tx = self._create_tx(tx_config)
        self.rx = self._create_rx(rx_config)

    def _create_tx(self, config) -> Optional[TXInterface]:
        tx_type = config.get(CONF_TYPE)
        if tx_type == HUB_TYPE_LOCAL_USB:
            return LocalUSBTX(config.get(CONF_INDEX, 0))
        elif tx_type == HUB_TYPE_ESPHOME:
            return ESPHomeTX(self.hass, config.get(CONF_ENTITY_ID))
        elif tx_type == HUB_TYPE_WEBHOOK:
            return WebhookTX(config.get("url"))
        elif tx_type == HUB_TYPE_NATURE_REMO:
            return NatureRemoTX(config.get("access_token"), config.get("appliance_id"), config.get("signal_id"))
        elif tx_type == HUB_TYPE_MOCK:
            return MockTX()
        return None

    def _create_rx(self, config) -> Optional[RXInterface]:
        rx_type = config.get(CONF_TYPE)
        
        def handle_received_code(code: str):
            _LOGGER.debug("Hub %s received IR code: %s", self.hub_id, code)
            self.hass.bus.async_fire(EVENT_IR_RECEIVED, {
                ATTR_RECEIVER: self.hub_id,
                ATTR_CODE: code
            })

        if rx_type == HUB_TYPE_LOCAL_USB:
            return LocalUSBRX(self.hub_id, handle_received_code, config.get(CONF_INDEX, 0))
        elif rx_type == HUB_TYPE_WEBHOOK:
            return WebhookRX(self.hub_id, handle_received_code, config.get(CONF_WEBHOOK_ID))
        elif rx_type == HUB_TYPE_NATURE_REMO:
            return NatureRemoRX(self.hub_id, handle_received_code, config.get("access_token"), config.get(CONF_POLL_INTERVAL, 1.0))
        return None

    async def async_setup(self):
        if self.rx:
            await self.rx.async_setup(self.hass)

    async def async_teardown(self):
        if self.rx:
            await self.rx.async_teardown(self.hass)

    async def async_send(self, code: str, force_aeha_tx: bool = False):
        if self.tx:
            await self.tx.async_send(code, force_aeha_tx)

# --- TX Implementations ---

class LocalUSBTX(TXInterface):
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
        
        async with self._lock:
            await asyncio.to_thread(self._do_send, packet)

    def _do_send(self, packet):
        dev = self._open_device()
        if dev:
            try: dev.write(self._endpoint_out, packet, timeout=1000)
            except: self._dev = None

class ESPHomeTX(TXInterface):
    def __init__(self, hass, entity_id):
        self.hass = hass
        self.entity_id = entity_id
    async def async_send(self, code: str, force_aeha_tx: bool = False):
        parts = code.split('_')
        if len(parts) != 2: return
        protocol, signal = parts
        await self.hass.services.async_call("remote", "send_command", {
            "entity_id": self.entity_id, "command": f"protocol: {protocol}, data: 0x{signal}"
        }, blocking=True)

class WebhookTX(TXInterface):
    def __init__(self, url):
        self.url = url
    async def async_send(self, code: str, force_aeha_tx: bool = False):
        import aiohttp
        async with aiohttp.ClientSession() as session:
            try:
                await session.post(self.url, json={"code": code}, timeout=10)
            except: pass

class NatureRemoTX(TXInterface):
    def __init__(self, token, appliance_id, signal_id):
        self.token = token
    async def async_send(self, code: str, force_aeha_tx: bool = False):
        # Placeholder for Nature Remo TX if needed
        _LOGGER.warning("Nature Remo TX not fully implemented yet")

class MockTX(TXInterface):
    async def async_send(self, code: str, force_aeha_tx: bool = False):
        _LOGGER.info("[MOCK] Sending: %s", code)

# --- RX Implementations ---

class LocalUSBRX(RXInterface):
    def __init__(self, hub_id, callback_fn, index=0):
        super().__init__(hub_id, callback_fn)
        self.index = index
        self._running = False
        self._vid = 0x22ea
        self._pid = 0x001e
        self._interface = 3
        self._endpoint_in = 0x83

    async def async_setup(self, hass: HomeAssistant):
        self._running = True
        asyncio.create_task(self._run_loop())

    async def async_teardown(self, hass: HomeAssistant):
        self._running = False

    async def _run_loop(self):
        while self._running:
            code = await asyncio.to_thread(self._poll_usb)
            if code:
                self.callback_fn(code)
            await asyncio.sleep(0.1)

    def _poll_usb(self):
        import usb.core
        import usb.util
        dev = usb.core.find(idVendor=self._vid, idProduct=self._pid)
        if not dev: return None
        try:
            # Note: This is a simplified polling. 
            # Real hardware might need specific handshakes or report parsing.
            data = dev.read(self._endpoint_in, 64, timeout=500)
            if data and data[0] == 0x61: # Example prefix
                # Process data to code string
                return "NEC_REPRODUCED" # Placeholder
        except: pass
        return None

class WebhookRX(RXInterface):
    def __init__(self, hub_id, callback_fn, webhook_id):
        super().__init__(hub_id, callback_fn)
        self.webhook_id = webhook_id

    async def async_setup(self, hass: HomeAssistant):
        webhook_register(hass, DOMAIN, f"IR Hub {self.hub_id}", self.webhook_id, self._handle_webhook)

    async def async_teardown(self, hass: HomeAssistant):
        webhook_unregister(hass, self.webhook_id)

    async def _handle_webhook(self, hass, webhook_id, request):
        try:
            data = await request.json()
            code = data.get("code")
            if code:
                self.callback_fn(code)
        except: pass

class NatureRemoRX(RXInterface):
    def __init__(self, hub_id, callback_fn, token, interval):
        super().__init__(hub_id, callback_fn)
        self.token = token
        self.interval = interval
        self._stop_polling = None

    async def async_setup(self, hass: HomeAssistant):
        async def poll(now):
            await self._poll_now()
        self._stop_polling = async_track_time_interval(hass, poll, timedelta(seconds=self.interval))

    async def async_teardown(self, hass: HomeAssistant):
        if self._stop_polling:
            self._stop_polling()

    async def _poll_now(self):
        import aiohttp
        # Nature Remo Cloud API polling logic
        # GET /1/messages -> check latest signal
        pass
