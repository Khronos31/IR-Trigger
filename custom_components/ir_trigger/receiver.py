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
        self._dev = None
        self._thread = None
        self._vid = 0x22ea
        self._pid = 0x001e
        self._interface = 3
        self._endpoint_out = 0x04
        self._endpoint_in = 0x84
        self._pkt_size = 64

    async def async_setup(self):
        _LOGGER.info("Starting dedicated USB RX thread for %s (Index: %d)", self.receiver_id, self.index)
        self._running = True
        self._thread = threading.Thread(
            target=self._read_loop_blocking, 
            daemon=True, 
            name=f"IR_RX_{self.receiver_id}"
        )
        self._thread.start()

    async def async_teardown(self):
        self._running = False
        if self._dev:
            import usb.util
            try:
                # 受信待機モード解除 (0x53, 0x00)
                out_buf = bytearray([0xFF] * self._pkt_size)
                out_buf[0], out_buf[1] = 0x53, 0x00
                self._dev.write(self._endpoint_out, out_buf, timeout=1000)
                usb.util.dispose_resources(self._dev)
            except:
                pass
            self._dev = None

    def _open_device(self):
        import usb.core
        import usb.util
        devs = list(usb.core.find(find_all=True, idVendor=self._vid, idProduct=self._pid))
        if not devs or len(devs) <= self.index:
            return None
        dev = devs[self.index]
        try:
            if dev.is_kernel_driver_active(self._interface):
                dev.detach_kernel_driver(self._interface)
            usb.util.claim_interface(dev, self._interface)
            
            # 初期化: RECEIVE_WAIT_MODE_WAIT (0x53, 0x01)
            out_buf = bytearray([0xFF] * self._pkt_size)
            out_buf[0], out_buf[1] = 0x53, 0x01
            dev.write(self._endpoint_out, out_buf, timeout=1000)
            dev.read(self._endpoint_in, self._pkt_size, timeout=1000)
            return dev
        except Exception as e:
            _LOGGER.debug("Failed to open USB RX device %d: %s", self.index, e)
            return None

    def _normalize_ir_data(self, data) -> str:
        if len(data) < 3: return "RAW_UNKNOWN"
        format_id = data[0]
        total_bits = data[1] + data[2]
        valid_bytes = math.ceil(total_bits / 8)
        payload = data[3:] if len(data) < 3 + valid_bytes else data[3:3+valid_bytes]
        hex_payload = "".join(f"{b:02X}" for b in payload)

        prefixes = {1: "AEHA_", 2: "NEC_", 3: "SONY_", 4: "MITSUBISHI_"}
        prefix = prefixes.get(format_id, "DAIKIN_" if format_id in (5, 6) else "RAW_")
        return f"{prefix}{hex_payload}"

    def _read_loop_blocking(self):
        import usb.core
        while self._running:
            if not self._dev:
                self._dev = self._open_device()
                if not self._dev:
                    time.sleep(5)
                    continue

            try:
                try:
                    # 1. 待機モード開始 (Legacy方式: 毎回セット)
                    out_buf = bytearray([0xFF] * self._pkt_size)
                    out_buf[0], out_buf[1] = 0x53, 0x01
                    self._dev.write(self._endpoint_out, out_buf, timeout=1000)
                    self._dev.read(self._endpoint_in, self._pkt_size, timeout=1000)
                except usb.core.USBError as e:
                    if e.errno != 110: # ETIMEDOUT以外は外側のexceptへ
                        raise e
                    continue # タイムアウト時は安全にループの先頭へ戻る

                # 2. 読み取りループ
                received_code = None
                while self._running:
                    out_buf = bytearray([0xFF] * self._pkt_size)
                    out_buf[0] = 0x52
                    try:
                        self._dev.write(self._endpoint_out, out_buf, timeout=1000)
                        in_buf = self._dev.read(self._endpoint_in, self._pkt_size, timeout=1000)

                        if in_buf[0] == 0x52 and in_buf[1] != 0:
                            received_code = self._normalize_ir_data(in_buf[1:])
                            break
                    except usb.core.USBError as e:
                        if e.errno != 110: # 110 (ETIMEDOUT) は正常なので無視
                            raise e
                    time.sleep(0.01)

                if received_code:
                    self.hass.loop.call_soon_threadsafe(self._handle_code, received_code)

                try:
                    # 3. 待機モード終了 (これでバッファを強制クリア)
                    out_buf[0], out_buf[1] = 0x53, 0x00
                    self._dev.write(self._endpoint_out, out_buf, timeout=1000)
                    self._dev.read(self._endpoint_in, self._pkt_size, timeout=1000)
                except usb.core.USBError as e:
                    if e.errno != 110:
                        raise e

            except usb.core.USBError as e:
                # エラー時は再接続
                _LOGGER.debug("USB RX Error (reconnecting...): %s", e)
                if self._dev:
                    import usb.util
                    usb.util.dispose_resources(self._dev)
                self._dev = None
                time.sleep(1)
            except Exception as e:
                _LOGGER.error("Unexpected USB RX Error on %s: %s", self.receiver_id, e)
                if self._dev:
                    import usb.util
                    usb.util.dispose_resources(self._dev)
                self._dev = None
                time.sleep(1)

            time.sleep(0.1)

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
    if rx_type == RX_TYPE_USB_AD00020P:
        return USBad00020pRX(hass, receiver_id, config.get(CONF_INDEX, 0))
    elif rx_type == RX_TYPE_WEBHOOK:
        return WebhookRX(hass, receiver_id)
    elif rx_type == RX_TYPE_NATURE_REMO:
        return NatureRemoRX(
            hass, 
            receiver_id, 
            config.get("ip"), 
            config.get(CONF_POLL_INTERVAL, 1.0)
        )
    return None
