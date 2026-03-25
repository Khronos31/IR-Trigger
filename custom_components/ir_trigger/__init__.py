import logging
import os
import yaml

from homeassistant.core import HomeAssistant, ServiceCall, Event
from homeassistant.helpers.typing import ConfigType
import homeassistant.helpers.config_validation as cv
from homeassistant.components.webhook import async_register as webhook_register, async_unregister as webhook_unregister
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    EVENT_IR_RECEIVED,
    SERVICE_RELOAD,
    DICT_FILE_NAME,
    CONF_RECEIVER,
    CONF_CODE,
    CONF_MODE_ENTITY,
    CONF_TRANSMITTERS,
    CONF_DEVICES,
    CONF_MODES,
    CONF_TYPE,
    CONF_INDEX,
    CONF_ENTITY_ID,
    CONF_TRANSMITTER,
    CONF_BUTTONS,
    CONF_BIND,
    CONF_REMAP,
    CONF_SOURCE,
    CONF_TARGET,
    CONF_SERVICE,
    CONF_DATA,
    ATTR_RECEIVER,
    ATTR_CONTROLLER,
    ATTR_BUTTON,
    ATTR_CODE,
    SIGNAL_NEW_RECEIVER,
    SIGNAL_UPDATE_SENSOR,
    SIGNAL_LOAD_COMPLETE,
)
from .transmitter import LocalUSBTransmitter, ESPHomeTransmitter, MockTransmitter

_LOGGER = logging.getLogger(__name__)

# Integration configuration schema
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

class IRTriggerData:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.dictionary = {}
        self.known_receivers = set()
        self.mode_entity = None
        self.transmitters = {}
        self.devices = {}
        self.modes_map = {} # mode_name -> { source_code -> action }
        self.loaded = False

    def load_config(self):
        config_path = self.hass.config.path(DICT_FILE_NAME)
        if not os.path.exists(config_path):
            _LOGGER.warning("Config file %s not found.", config_path)
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                
            self.mode_entity = config.get(CONF_MODE_ENTITY)
            
            # 1. Setup Transmitters
            self._setup_transmitters(config.get(CONF_TRANSMITTERS, {}))
            
            # 2. Setup Devices & Reverse Dictionary for RX
            self.devices = config.get(CONF_DEVICES, {})
            self._build_reverse_dictionary()
            
            # 3. Setup Modes (Binding & Remapping)
            self._setup_modes(config.get(CONF_MODES, {}))
            
            self.loaded = True
            _LOGGER.info("IR-Trigger configuration loaded successfully")
            async_dispatcher_send(self.hass, SIGNAL_LOAD_COMPLETE)
            
        except Exception as e:
            _LOGGER.error("Error loading %s: %s", config_path, e)

    def _setup_transmitters(self, tx_config):
        self.transmitters = {}
        for tx_id, tx_info in tx_config.items():
            tx_type = tx_info.get(CONF_TYPE)
            if tx_type == "local_usb":
                self.transmitters[tx_id] = LocalUSBTransmitter(tx_info.get(CONF_INDEX, 0))
            elif tx_type == "esphome":
                self.transmitters[tx_id] = ESPHomeTransmitter(self.hass, tx_info.get(CONF_ENTITY_ID))
            else:
                _LOGGER.warning("Unknown transmitter type %s for %s, using mock", tx_type, tx_id)
                self.transmitters[tx_id] = MockTransmitter()

    def _build_reverse_dictionary(self):
        # Build dictionary for RX lookup: code -> {controller, button}
        self.dictionary = {}
        for device_id, device_info in self.devices.items():
            name = device_info.get("name", device_id)
            for button_name, code in device_info.get(CONF_BUTTONS, {}).items():
                self.dictionary[code] = {
                    "controller": name,
                    "button": button_name
                }

    def _setup_modes(self, modes_config):
        self.modes_map = {}
        for mode_name, mode_info in modes_config.items():
            mapping = {}
            
            # Handle bind (automatic mapping by key name)
            for bind_item in mode_info.get(CONF_BIND, []):
                source_id = bind_item.get(CONF_SOURCE)
                target_id = bind_item.get(CONF_TARGET)
                
                source_dev = self.devices.get(source_id)
                target_dev = self.devices.get(target_id)
                
                if source_dev and target_dev:
                    source_keys = source_dev.get(CONF_BUTTONS, {})
                    target_keys = target_dev.get(CONF_BUTTONS, {})
                    
                    for key_name, source_code in source_keys.items():
                        if key_name in target_keys:
                            target_code = target_keys[key_name]
                            target_tx_id = target_dev.get(CONF_TRANSMITTER)
                            mapping[source_code] = {
                                "type": "transmit",
                                "code": target_code,
                                "transmitter": target_tx_id
                            }
            
            # Handle remap (manual mapping)
            for source_code, action in mode_info.get(CONF_REMAP, {}).items():
                mapping[source_code] = {
                    "type": "action",
                    "action": action
                }
                
            self.modes_map[mode_name] = mapping

    def get_info(self, code: str):
        info = self.dictionary.get(code, {})
        return {
            ATTR_CONTROLLER: info.get("controller", "Undefined"),
            ATTR_BUTTON: info.get("button", "Undefined")
        }

    async def async_register_devices(self):
        """Register transmitters and target devices in HA device registry."""
        dev_reg = dr.async_get(self.hass)
        
        # Register Transmitters
        for tx_id, tx_info in self.transmitters.items():
            # In a real scenario, we'd get the name from the YAML transmitter definition
            # Let's assume we store the raw config too or just use the ID
            dev_reg.async_get_or_create(
                config_entry_id=DOMAIN, # This might need to be specific
                identifiers={(DOMAIN, tx_id)},
                name=f"Transmitter {tx_id}",
                manufacturer="IR-Trigger",
                model="IR-Transmitter Hub",
            )

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the IR-Trigger component."""
    
    ir_data = IRTriggerData(hass)
    await hass.async_add_executor_job(ir_data.load_config)
    hass.data[DOMAIN] = ir_data

    # Setup Reload Service
    async def handle_reload(call: ServiceCall):
        """Handle reload service call."""
        _LOGGER.info("Reloading IR configuration...")
        await hass.async_add_executor_job(ir_data.load_config)
    
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

            info = ir_data.get_info(code)
            
            event_data = {
                ATTR_RECEIVER: receiver,
                ATTR_CODE: code,
                ATTR_CONTROLLER: info[ATTR_CONTROLLER],
                ATTR_BUTTON: info[ATTR_BUTTON],
            }
            
            hass.bus.async_fire(EVENT_IR_RECEIVED, event_data)
            
        except Exception as e:
            _LOGGER.error("Error processing webhook: %s", e)

    webhook_register(
        hass, DOMAIN, "IR Trigger Webhook", f"{DOMAIN}_webhook", handle_webhook
    )

    # Setup Event Listener for Dynamic Routing
    async def handle_ir_event(event: Event):
        receiver = event.data.get(ATTR_RECEIVER)
        code = event.data.get(ATTR_CODE)
        
        if not receiver or not code: return

        # 1. Update Sensors (Legacy/Status Monitoring)
        info = ir_data.get_info(code)
        controller = event.data.get(ATTR_CONTROLLER) or info[ATTR_CONTROLLER]
        button = event.data.get(ATTR_BUTTON) or info[ATTR_BUTTON]

        if receiver not in ir_data.known_receivers:
            ir_data.known_receivers.add(receiver)
            async_dispatcher_send(hass, SIGNAL_NEW_RECEIVER, receiver)

        sensor_data = {ATTR_CODE: code, ATTR_CONTROLLER: controller, ATTR_BUTTON: button}
        async_dispatcher_send(hass, SIGNAL_UPDATE_SENSOR, receiver, sensor_data)

        # 2. Dynamic Routing Logic
        if not ir_data.mode_entity: return
        
        current_mode = hass.states.get(ir_data.mode_entity)
        if not current_mode: return
        
        mode_name = current_mode.state
        if mode_name not in ir_data.modes_map: return
        
        mapping = ir_data.modes_map[mode_name]
        if code not in mapping: return
        
        action = mapping[code]
        _LOGGER.debug("Routing IR code %s in mode %s: %s", code, mode_name, action)
        
        if action["type"] == "transmit":
            tx_id = action["transmitter"]
            transmitter = ir_data.transmitters.get(tx_id)
            if transmitter:
                await transmitter.async_send(action["code"])
        
        elif action["type"] == "action":
            # Manual remap: HA service call
            act_info = action["action"]
            domain, service = act_info[CONF_SERVICE].split(".")
            await hass.services.async_call(
                domain, service, act_info.get(CONF_DATA, {}), blocking=False
            )

    hass.bus.async_listen(EVENT_IR_RECEIVED, handle_ir_event)

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "import"}, data={}
        )
    )

    return True

async def async_setup_entry(hass, entry):
    """Set up IR-Trigger from a config entry."""
    ir_data = hass.data[DOMAIN]
    await ir_data.async_register_devices()
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])
    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, ["sensor", "button"])
