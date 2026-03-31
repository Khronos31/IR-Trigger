import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Callable, Optional
from datetime import timedelta
from aiohttp import web

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.webhook import async_register as webhook_register, async_unregister as webhook_unregister
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    EVENT_IR_RECEIVED,
    ATTR_RECEIVER,
    ATTR_CODE,
    RX_TYPE_USB_AD00020P,
    RX_TYPE_WEBHOOK,
    RX_TYPE_NATURE_REMO,
    CONF_TYPE,
    CONF_INDEX,
    CONF_POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

class RXInterface(ABC):
    """Base class for IR Receivers."""
    def __init__(self, hass: HomeAssistant, receiver_id: str):
        self.hass = hass
        self.receiver_id = receiver_id

    @abstractmethod
    async def async_setup(self):
        pass

    @abstractmethod
    async def async_teardown(self):
        pass

    def _handle_code(self, code: str):
        """Fire event when IR code is received."""
        _LOGGER.debug("Receiver %s received IR code: %s", self.receiver_id, code)
        self.hass.bus.async_fire(EVENT_IR_RECEIVED, {
            ATTR_RECEIVER: self.receiver_id,
            ATTR_CODE: code
        })

class USBad00020pRX(RXInterface):
    def __init__(self, hass, receiver_id, index=0):
        super().__init__(hass, receiver_id)
        self.index = index
        self._running = False
        self._vid = 0x22ea
        self._pid = 0x001e
        self._interface = 3
        self._endpoint_in = 0x83

    async def async_setup(self):
        _LOGGER.info("Starting USB polling loop for receiver: %s (index: %d)", self.receiver_id, self.index)
        self._running = True
        asyncio.create_task(self._run_loop())

    async def async_teardown(self):
        self._running = False

    async def _run_loop(self):
        while self._running:
            code = await asyncio.to_thread(self._poll_usb)
            if code:
                self._handle_code(code)
            await asyncio.sleep(0.1)

    def _poll_usb(self):
        import usb.core
        try:
            dev = usb.core.find(idVendor=self._vid, idProduct=self._pid)
            if not dev: return None
            # Placeholder for actual hardware polling logic
            data = dev.read(self._endpoint_in, 64, timeout=500)
            if data and data[0] == 0x61:
                return "NEC_REPRODUCED" # Placeholder
        except: pass
        return None

class WebhookRX(RXInterface):
    def __init__(self, hass, receiver_id):
        super().__init__(hass, receiver_id)
        # Use receiver_id as webhook_id
        self.webhook_id = receiver_id

    async def async_setup(self):
        webhook_register(
            self.hass, 
            DOMAIN, 
            f"IR Receiver {self.receiver_id}", 
            self.webhook_id, 
            self._handle_webhook
        )
        _LOGGER.info("Registered webhook receiver: %s at /api/webhook/%s", self.receiver_id, self.webhook_id)

    async def async_teardown(self):
        webhook_unregister(self.hass, self.webhook_id)

    async def _handle_webhook(self, hass, webhook_id, request):
        try:
            data = await request.json()
            # Payload is now just {"code": "..."}
            code = data.get("code")
            if code:
                _LOGGER.info("Webhook received for %s: %s", self.receiver_id, code)
                self._handle_code(code)
                return web.Response(status=200, text="OK")
        except Exception as e:
            _LOGGER.error("Error processing webhook for %s: %s", self.receiver_id, e)
        return web.Response(status=400, text="Invalid Payload")

class NatureRemoRX(RXInterface):
    def __init__(self, hass, receiver_id, token, interval):
        super().__init__(hass, receiver_id)
        self.token = token
        self.interval = interval
        self._stop_polling = None

    async def async_setup(self):
        async def poll(now):
            await self._poll_now()
        self._stop_polling = async_track_time_interval(
            self.hass, poll, timedelta(seconds=self.interval)
        )

    async def async_teardown(self):
        if self._stop_polling:
            self._stop_polling()

    async def _poll_now(self):
        # Nature Remo Cloud API polling logic placeholder
        pass

def create_receiver(hass: HomeAssistant, receiver_id: str, config: dict) -> Optional[RXInterface]:
    rx_type = config.get(CONF_TYPE)
    if rx_type == RX_TYPE_USB_AD00020P:
        return USBad00020pRX(hass, receiver_id, config.get(CONF_INDEX, 0))
    elif rx_type == RX_TYPE_WEBHOOK:
        return WebhookRX(hass, receiver_id)
    elif rx_type == RX_TYPE_NATURE_REMO:
        return NatureRemoRX(
            hass, 
            receiver_id, 
            config.get("access_token"), 
            config.get(CONF_POLL_INTERVAL, 1.0)
        )
    return None
