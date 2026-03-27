import logging
import os

from homeassistant.core import HomeAssistant, ServiceCall, Event
from homeassistant.helpers.typing import ConfigType
import homeassistant.helpers.config_validation as cv
from homeassistant.components.webhook import async_register as webhook_register, async_unregister as webhook_unregister
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import device_registry as dr
from homeassistant.util.yaml import load_yaml

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
    CONF_NAME,
    CONF_LOCAL_RECEIVERS,
    CONF_REPEAT,
    CONF_FORCE_AEHA_TX,
    ATTR_RECEIVER,
    ATTR_DEVICE,
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
        self.transmitters_config = {} # transmitter_id -> config
        self.transmitters = {}        # transmitter_id -> instance
        self.devices = {}
        self.modes_map = {} # mode_name -> { source_code -> action }
        self.repeat_map = {} # mode_name -> [device_id]
        self.loaded = False

    def load_config(self):
        config_path = self.hass.config.path(DICT_FILE_NAME)
        if not os.path.exists(config_path):
            _LOGGER.warning("Config file %s not found.", config_path)
            return

        try:
            config = load_yaml(config_path)
            self.mode_entity = config.get(CONF_MODE_ENTITY)
            
            # 1. Setup Transmitters
            self.transmitters_config = config.get(CONF_TRANSMITTERS, {})
            self._setup_transmitters(self.transmitters_config)
            
            # 2. Setup Devices & Reverse Dictionary for RX
            self.devices = config.get(CONF_DEVICES, {})
            self._build_reverse_dictionary()
            
            # 3. Setup Modes (Binding, Remapping, Repeating)
            self._setup_modes(config.get(CONF_MODES, {}))
            
            self.loaded = True
            _LOGGER.info("IR-Trigger configuration loaded successfully")
            self.hass.add_job(async_dispatcher_send, self.hass, SIGNAL_LOAD_COMPLETE)
            
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
            elif tx_type == "webhook":
                self.transmitters[tx_id] = WebhookTransmitter(tx_info.get("url"))
            else:
                _LOGGER.warning("Unknown transmitter type %s for %s, using mock", tx_type, tx_id)
                self.transmitters[tx_id] = MockTransmitter()

    def _build_reverse_dictionary(self):
        # Build dictionary for RX lookup: code -> {device, button, device_id}
        self.dictionary = {}
        for device_id, device_info in self.devices.items():
            name = device_info.get(CONF_NAME, device_id)
            for button_name, code in device_info.get(CONF_BUTTONS, {}).items():
                self.dictionary[code] = {
                    "device": name,
                    "button": button_name,
                    "device_id": device_id
                }

    def _setup_modes(self, modes_config):
        self.modes_map = {}
        self.repeat_map = {}
        for mode_name, mode_info in modes_config.items():
            mapping = {}
            
            # Handle repeat
            self.repeat_map[mode_name] = mode_info.get(CONF_REPEAT, [])
            
            # Handle bind (automatic mapping by key name)
            bind_list = mode_info.get(CONF_BIND, [])
            if isinstance(bind_list, dict): # Handle single dict or list
                bind_list = [bind_list]
                
            for bind_item in bind_list:
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
                                "transmitter": target_tx_id,
                                "force_aeha_tx": target_dev.get(CONF_FORCE_AEHA_TX, False)
                            }
            
            # Handle remap (manual mapping)
            for source_code, actions in mode_info.get(CONF_REMAP, {}).items():
                if not isinstance(actions, list):
                    actions = [actions]
                
                mapping[source_code] = {
                    "type": "action",
                    "actions": actions
                }
                
            self.modes_map[mode_name] = mapping

    def get_info(self, code: str):
        info = self.dictionary.get(code, {})
        return {
            ATTR_DEVICE: info.get("device", "Undefined"),
            ATTR_BUTTON: info.get("button", "Undefined"),
            "device_id": info.get("device_id")
        }

    async def async_register_devices(self, entry):
        """Register transmitters and target devices in HA device registry."""
        dev_reg = dr.async_get(self.hass)
        
        # Register Transmitters
        for tx_id, tx_info in self.transmitters_config.items():
            dev_reg.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, tx_id)},
                name=tx_info.get(CONF_NAME, tx_id),
                manufacturer="IR-Trigger",
                model="IR-Transmitter Hub",
            )
        
        # Target devices are registered by button.py using via_device

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
                ATTR_DEVICE: info[ATTR_DEVICE],
                ATTR_BUTTON: info[ATTR_BUTTON],
            }
            
            hass.bus.async_fire(EVENT_IR_RECEIVED, event_data)
            
        except Exception as e:
            _LOGGER.error("Error processing webhook: %s", e)

    webhook_register(
        hass, DOMAIN, "IR Trigger Webhook", f"{DOMAIN}_webhook", handle_webhook
    )

    # Setup Event Listener for Dynamic Routing & Auto-Repeater
    async def handle_ir_event(event: Event):
        receiver = event.data.get(ATTR_RECEIVER)
        code = event.data.get(ATTR_CODE)
        
        if not receiver or not code: return

        # 1. Update Sensors (Legacy/Status Monitoring)
        info = ir_data.get_info(code)
        device_name = event.data.get(ATTR_DEVICE) or info[ATTR_DEVICE]
        device_id = info.get("device_id")
        button = event.data.get(ATTR_BUTTON) or info[ATTR_BUTTON]

        if receiver not in ir_data.known_receivers:
            ir_data.known_receivers.add(receiver)
            async_dispatcher_send(hass, SIGNAL_NEW_RECEIVER, receiver)

        sensor_data = {ATTR_CODE: code, ATTR_DEVICE: device_name, ATTR_BUTTON: button}
        async_dispatcher_send(hass, SIGNAL_UPDATE_SENSOR, receiver, sensor_data)

        # 2. Global "always" mode for repeating
        modes_to_check = ["always"]
        if ir_data.mode_entity:
            current_mode_state = hass.states.get(ir_data.mode_entity)
            if current_mode_state:
                modes_to_check.append(current_mode_state.state)

        for mode_name in modes_to_check:
            if mode_name not in ir_data.modes_map and mode_name not in ir_data.repeat_map:
                continue

            # 2.1. Auto-Repeater Logic
            if device_id and device_id in ir_data.repeat_map.get(mode_name, []):
                target_dev_info = ir_data.devices.get(device_id)
                if target_dev_info:
                    tx_id = target_dev_info.get(CONF_TRANSMITTER)
                    transmitter = ir_data.transmitters.get(tx_id)
                    tx_config = ir_data.transmitters_config.get(tx_id, {})
                    local_receivers = tx_config.get(CONF_LOCAL_RECEIVERS, [])
                    
                    if receiver in local_receivers:
                        _LOGGER.warning(
                            "Loop Prevention: Dropped repeat for %s from local receiver %s on transmitter %s",
                            device_id, receiver, tx_id
                        )
                    elif transmitter:
                        _LOGGER.info("Auto-Repeating IR code %s for %s", code, device_id)
                        force_aeha = target_dev_info.get(CONF_FORCE_AEHA_TX, False)
                        await transmitter.async_send(code, force_aeha_tx=force_aeha)

            # 2.2. Dynamic Routing Logic (bind/remap)
            mapping = ir_data.modes_map.get(mode_name, {})
            if code in mapping:
                action = mapping[code]
                _LOGGER.debug("Routing IR code %s in mode %s: %s", code, mode_name, action)
                
                if action["type"] == "transmit":
                    tx_id = action["transmitter"]
                    transmitter = ir_data.transmitters.get(tx_id)
                    if transmitter:
                        await transmitter.async_send(
                            action["code"], 
                            force_aeha_tx=action.get("force_aeha_tx", False)
                        )
                
                elif action["type"] == "action":
                    for act_info in action["actions"]:
                        domain, service = act_info[CONF_SERVICE].split(".")
                        await hass.services.async_call(
                            domain, service, act_info.get(CONF_DATA, {}), 
                            target=act_info.get("target"),
                            blocking=False
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
    await ir_data.async_register_devices(entry)
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])
    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, ["sensor", "button"])
