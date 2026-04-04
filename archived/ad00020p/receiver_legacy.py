import logging
import asyncio
import threading
import time
import math
from abc import ABC, abstractmethod
from typing import Callable, Optional
from datetime import timedelta
from aiohttp import web
# ... (rest of imports)

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.webhook import async_register as webhook_register, async_unregister as webhook_unregister
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import converter

from .const import (
    DOMAIN,
    EVENT_IR_RECEIVED,
    ATTR_RECEIVER,
    ATTR_CODE,
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
            code = data.get("code")
            raw = data.get("raw")

            # If raw pulses are provided, convert to code string
            if raw and isinstance(raw, list):
                _LOGGER.debug("RAW payload received from %s: %s", self.receiver_id, raw)
                code = converter.raw_to_code(raw)

            if code:
                _LOGGER.info("Webhook received for %s: %s", self.receiver_id, code)
                self._handle_code(code)
                return web.Response(status=200, text="OK")
        except Exception as e:
            _LOGGER.error("Error processing webhook for %s: %s", self.receiver_id, e)
        return web.Response(status=400, text="Invalid Payload")

class NatureRemoRX(RXInterface):
    def __init__(self, hass, receiver_id, ip, interval):
        super().__init__(hass, receiver_id)
        self.ip = ip
        self.interval = interval
        self._stop_polling = None
        self._last_data = None

    async def async_setup(self):
        async def poll(now):
            await self._poll_now()
        self._stop_polling = async_track_time_interval(
            self.hass, poll, timedelta(seconds=self.interval)
        )
        _LOGGER.info("Started Nature Remo local polling for %s at %s (interval: %s)", 
                     self.receiver_id, self.ip, self.interval)

    async def async_teardown(self):
        if self._stop_polling:
            self._stop_polling()

    async def _poll_now(self):
        url = f"http://{self.ip}/messages"
        headers = {"X-Requested-With": "local"}
        session = async_get_clientsession(self.hass)
        
        try:
            async with asyncio.timeout(2):
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return
                    
                    data = await resp.json()
                    # Nature Remo returns pulses in 'data' field
                    pulses = data.get("data")
                    
                    if not pulses:
                        return
                    
                    # Deduplication
                    if pulses == self._last_data:
                        return
                    
                    self._last_data = pulses
                    _LOGGER.debug("Nature Remo %s received new signal: %s", self.receiver_id, pulses)
                    
                    # Convert raw pulses to code
                    code = converter.raw_to_code(pulses)
                    if code:
                        self._handle_code(code)

        except asyncio.TimeoutError:
            _LOGGER.debug("Nature Remo %s poll timeout", self.receiver_id)
        except Exception as e:
            _LOGGER.error("Error polling Nature Remo %s: %s", self.receiver_id, e)

def create_receiver(hass: HomeAssistant, receiver_id: str, config: dict) -> Optional[RXInterface]:
    rx_type = config.get(CONF_TYPE)
    if rx_type == RX_TYPE_WEBHOOK:
        return WebhookRX(hass, receiver_id)
    elif rx_type == RX_TYPE_NATURE_REMO:
        return NatureRemoRX(
            hass, 
            receiver_id, 
            config.get("ip"), 
            config.get(CONF_POLL_INTERVAL, 1.0)
        )
    return None
