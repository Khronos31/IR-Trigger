import logging
import os
import yaml

from homeassistant.core import HomeAssistant, ServiceCall, Event
from homeassistant.helpers.typing import ConfigType
import homeassistant.helpers.config_validation as cv
from homeassistant.components.webhook import async_register as webhook_register, async_unregister as webhook_unregister
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    EVENT_IR_RECEIVED,
    SERVICE_RELOAD,
    DICT_FILE_NAME,
    CONF_RECEIVER,
    CONF_CODE,
    ATTR_RECEIVER,
    ATTR_CONTROLLER,
    ATTR_BUTTON,
    ATTR_CODE,
    SIGNAL_NEW_RECEIVER,
    SIGNAL_UPDATE_SENSOR,
)

_LOGGER = logging.getLogger(__name__)

# Integration configuration schema
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

class IRTriggerData:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.dictionary = {}
        self.known_receivers = set()

    def load_dictionary(self):
        config_path = self.hass.config.path(DICT_FILE_NAME)
        if not os.path.exists(config_path):
            _LOGGER.warning("Dictionary file %s not found. Using empty dictionary.", config_path)
            self.dictionary = {}
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    self.dictionary = data
                    _LOGGER.info("Successfully loaded IR dictionary from %s", config_path)
                else:
                    _LOGGER.error("Invalid format in %s. Expected a dictionary.", config_path)
                    self.dictionary = {}
        except Exception as e:
            _LOGGER.error("Error reading %s: %s", config_path, e)
            self.dictionary = {}

    def get_info(self, code: str):
        info = self.dictionary.get(code, {})
        return {
            ATTR_CONTROLLER: info.get("controller", "Undefined"),
            ATTR_BUTTON: info.get("button", "Undefined")
        }


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the IR-Trigger component."""
    
    ir_data = IRTriggerData(hass)
    await hass.async_add_executor_job(ir_data.load_dictionary)
    hass.data[DOMAIN] = ir_data

    # Setup Reload Service
    async def handle_reload(call: ServiceCall):
        """Handle reload service call."""
        _LOGGER.info("Reloading IR dictionary...")
        await hass.async_add_executor_job(ir_data.load_dictionary)
    
    hass.services.async_register(DOMAIN, SERVICE_RELOAD, handle_reload)

    # Setup Webhook
    async def handle_webhook(hass: HomeAssistant, webhook_id: str, request):
        """Handle incoming webhook payload."""
        try:
            data = await request.json()
            receiver = data.get(CONF_RECEIVER)
            code = data.get(CONF_CODE)
            
            if not receiver or not code:
                _LOGGER.error("Invalid webhook payload. Missing receiver or code.")
                return

            # Lookup dictionary
            info = ir_data.get_info(code)
            
            event_data = {
                ATTR_RECEIVER: receiver,
                ATTR_CODE: code,
                ATTR_CONTROLLER: info[ATTR_CONTROLLER],
                ATTR_BUTTON: info[ATTR_BUTTON],
            }
            
            # Fire event
            hass.bus.async_fire(EVENT_IR_RECEIVED, event_data)
            _LOGGER.debug("Webhook triggered event: %s", event_data)
            
        except Exception as e:
            _LOGGER.error("Error processing webhook: %s", e)

    webhook_register(
        hass,
        DOMAIN,
        "IR Trigger Webhook",
        f"{DOMAIN}_webhook",
        handle_webhook
    )

    # Setup Event Listener (for ESPHome or Webhook fired events)
    async def handle_ir_event(event: Event):
        receiver = event.data.get(ATTR_RECEIVER)
        code = event.data.get(ATTR_CODE)
        
        if not receiver or not code:
            return

        controller = event.data.get(ATTR_CONTROLLER)
        button = event.data.get(ATTR_BUTTON)

        # If ESPHome fires this without controller/button, lookup from dict
        if controller is None or button is None:
            info = ir_data.get_info(code)
            controller = info[ATTR_CONTROLLER]
            button = info[ATTR_BUTTON]

        # Register receiver if new, so sensor.py can create entities
        if receiver not in ir_data.known_receivers:
            ir_data.known_receivers.add(receiver)
            async_dispatcher_send(hass, SIGNAL_NEW_RECEIVER, receiver)

        # Update sensors
        sensor_data = {
            ATTR_CODE: code,
            ATTR_CONTROLLER: controller,
            ATTR_BUTTON: button
        }
        async_dispatcher_send(hass, SIGNAL_UPDATE_SENSOR, receiver, sensor_data)

    hass.bus.async_listen(EVENT_IR_RECEIVED, handle_ir_event)

    # Setup platforms (sensor)
    # We use async_create_task to setup the platform
    hass.async_create_task(
        hass.helpers.discovery.async_load_platform("sensor", DOMAIN, {"setup": True}, config)
    )

    return True
