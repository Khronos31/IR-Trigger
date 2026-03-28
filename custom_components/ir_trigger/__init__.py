import logging
import os
from pathlib import Path

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
    CONF_GLOBAL,
    CONF_STATE_MACHINES,
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
    CONF_DOMAIN,
    CONF_MAPPING,
    CONF_TEMPLATE,
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

def deep_merge(base, overrides):
    """Deep merge two dictionaries."""
    for key, value in overrides.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base

class IRTriggerData:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.dictionary = {}
        self.known_receivers = set()
        self.transmitters_config = {} # transmitter_id -> config
        self.transmitters = {}        # transmitter_id -> instance
        self.devices = {}
        self.global_repeat = []
        self.global_remap = {} # source_code -> action
        self.state_machines = [] # List of { mode_entity, modes_map: { mode_name -> { source_code -> action } } }
        self.loaded = False

    def load_config(self):
        config_path = self.hass.config.path(DICT_FILE_NAME)
        if not os.path.exists(config_path):
            _LOGGER.warning("Config file %s not found.", config_path)
            return

        try:
            config = load_yaml(config_path)
            
            # 1. Setup Transmitters
            self.transmitters_config = config.get(CONF_TRANSMITTERS, {})
            self._setup_transmitters(self.transmitters_config)
            
            # 2. Setup Devices & Reverse Dictionary for RX
            devices_raw = config.get(CONF_DEVICES, {})
            self.devices = self._process_devices(devices_raw)
            self._build_reverse_dictionary()
            
            # 3. Setup Routing (Global & State Machines)
            self._setup_routing(config)
            
            self.loaded = True
            _LOGGER.info("IR-Trigger configuration loaded successfully")
            self.hass.add_job(async_dispatcher_send, self.hass, SIGNAL_LOAD_COMPLETE)
            
        except Exception as e:
            _LOGGER.error("Error loading %s: %s", config_path, e)
            import traceback
            _LOGGER.error(traceback.format_exc())

    def _process_devices(self, devices_raw):
        processed_devices = {}
        user_remotes_dir = Path(self.hass.config.config_dir) / "ir_trigger_remotes"
        official_remotes_dir = Path(__file__).parent / "remotes"

        for device_id, device_info in devices_raw.items():
            template_name = device_info.get(CONF_TEMPLATE)
            final_device_info = {}
            
            if template_name:
                template_file = None
                search_filename = f"{template_name}.yaml"
                for search_dir in [user_remotes_dir, official_remotes_dir]:
                    if search_dir.exists():
                        found = list(search_dir.rglob(search_filename))
                        if found:
                            template_file = found[0]
                            break
                if template_file:
                    try:
                        final_device_info = load_yaml(str(template_file))
                    except Exception as e:
                        _LOGGER.error("Error loading template %s: %s", template_file, e)
            
            deep_merge(final_device_info, device_info)
            processed_devices[device_id] = final_device_info
            
        return processed_devices

    def _setup_transmitters(self, tx_config):
        self.transmitters = {}
        for tx_id, tx_info in tx_config.items():
            tx_type = tx_info.get(CONF_TYPE)
            if tx_type == "local_usb":
                self.transmitters[tx_id] = LocalUSBTransmitter(tx_info.get(CONF_INDEX, 0))
            elif tx_type == "esphome":
                self.transmitters[tx_id] = ESPHomeTransmitter(self.hass, tx_info.get(CONF_ENTITY_ID))
            else:
                self.transmitters[tx_id] = MockTransmitter()

    def _build_reverse_dictionary(self):
        self.dictionary = {}
        for device_id, device_info in self.devices.items():
            name = device_info.get(CONF_NAME, device_id)
            for button_name, code in device_info.get(CONF_BUTTONS, {}).items():
                self.dictionary[code] = {"device": name, "button": button_name, "device_id": device_id}

    def _setup_routing(self, config):
        # 1. Global Setup
        global_config = config.get(CONF_GLOBAL, {})
        self.global_repeat = global_config.get(CONF_REPEAT, [])
        self.global_remap = self._parse_remap(global_config.get(CONF_REMAP, {}))

        # 2. State Machines Setup
        self.state_machines = []
        sm_configs = config.get(CONF_STATE_MACHINES, [])
        for sm_config in sm_configs:
            mode_entity = sm_config.get(CONF_MODE_ENTITY)
            modes_raw = sm_config.get(CONF_MODES, {})
            modes_map = {}
            for mode_name, mode_info in modes_raw.items():
                # Priority: Remap then Bind
                mapping = self._parse_remap(mode_info.get(CONF_REMAP, {}))
                bind_mapping = self._parse_bind(mode_info.get(CONF_BIND, []))
                # Merge bind into mapping, but keep existing remaps (priority)
                for code, action in bind_mapping.items():
                    if code not in mapping:
                        mapping[code] = action
                modes_map[mode_name] = mapping
            
            self.state_machines.append({
                "mode_entity": mode_entity,
                "modes_map": modes_map
            })

    def _parse_remap(self, remap_config):
        mapping = {}
        for source_code, actions in remap_config.items():
            if not isinstance(actions, list):
                actions = [actions]
            
            processed_actions = []
            for act in actions:
                if CONF_SERVICE in act:
                    processed_actions.append({"type": "service", "action": act})
                elif "code" in act:
                    processed_actions.append({"type": "transmit", "action": act})
            
            if processed_actions:
                mapping[source_code] = processed_actions
        return mapping

    def _parse_bind(self, bind_list):
        if isinstance(bind_list, dict):
            bind_list = [bind_list]
        
        mapping = {}
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
                        mapping[source_code] = [{
                            "type": "transmit",
                            "action": {
                                "code": target_keys[key_name],
                                "transmitter": target_dev.get(CONF_TRANSMITTER),
                                "force_aeha_tx": target_dev.get(CONF_FORCE_AEHA_TX, False)
                            }
                        }]
        return mapping

    def get_info(self, code: str):
        info = self.dictionary.get(code, {})
        return {
            ATTR_DEVICE: info.get("device", "Undefined"),
            ATTR_BUTTON: info.get("button", "Undefined"),
            "device_id": info.get("device_id")
        }

    async def async_register_devices(self, entry):
        dev_reg = dr.async_get(self.hass)
        for tx_id, tx_info in self.transmitters_config.items():
            dev_reg.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, tx_id)},
                name=tx_info.get(CONF_NAME, tx_id),
                manufacturer="IR-Trigger",
                model="IR-Transmitter Hub",
            )

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    ir_data = IRTriggerData(hass)
    await hass.async_add_executor_job(ir_data.load_config)
    hass.data[DOMAIN] = ir_data

    async def handle_reload(call: ServiceCall):
        _LOGGER.info("Reloading IR configuration...")
        await hass.async_add_executor_job(ir_data.load_config)
    hass.services.async_register(DOMAIN, SERVICE_RELOAD, handle_reload)

    async def handle_webhook(hass: HomeAssistant, webhook_id: str, request):
        try:
            data = await request.json()
            receiver = data.get(CONF_RECEIVER)
            code = data.get(CONF_CODE)
            if not receiver or not code: return
            info = ir_data.get_info(code)
            event_data = {ATTR_RECEIVER: receiver, ATTR_CODE: code, ATTR_DEVICE: info[ATTR_DEVICE], ATTR_BUTTON: info[ATTR_BUTTON]}
            hass.bus.async_fire(EVENT_IR_RECEIVED, event_data)
        except Exception as e:
            _LOGGER.error("Error processing webhook: %s", e)

    webhook_register(hass, DOMAIN, "IR Trigger Webhook", f"{DOMAIN}_webhook", handle_webhook)

    async def handle_ir_event(event: Event):
        receiver = event.data.get(ATTR_RECEIVER)
        code = event.data.get(ATTR_CODE)
        if not receiver or not code: return

        info = ir_data.get_info(code)
        device_id = info.get("device_id")
        
        if receiver not in ir_data.known_receivers:
            ir_data.known_receivers.add(receiver)
            async_dispatcher_send(hass, SIGNAL_NEW_RECEIVER, receiver)
        async_dispatcher_send(hass, SIGNAL_UPDATE_SENSOR, receiver, {ATTR_CODE: code, ATTR_DEVICE: info[ATTR_DEVICE], ATTR_BUTTON: info[ATTR_BUTTON]})

        # --- New Routing Engine ---

        # 1. Global Repeat (Independent)
        if device_id and device_id in ir_data.global_repeat:
            target_dev_info = ir_data.devices.get(device_id)
            if target_dev_info:
                tx_id = target_dev_info.get(CONF_TRANSMITTER)
                transmitter = ir_data.transmitters.get(tx_id)
                tx_config = ir_data.transmitters_config.get(tx_id, {})
                if receiver not in tx_config.get(CONF_LOCAL_RECEIVERS, []) and transmitter:
                    _LOGGER.info("Auto-Repeating IR code %s for %s", code, device_id)
                    await transmitter.async_send(code, force_aeha_tx=target_dev_info.get(CONF_FORCE_AEHA_TX, False))

        # 2. Global Remap (Exclusive)
        if code in ir_data.global_remap:
            _LOGGER.debug("Matched Global Remap for %s", code)
            await execute_actions(hass, ir_data, ir_data.global_remap[code])
            return # BREAK: Do not evaluate state machines

        # 3. State Machines (Independent Machines, Exclusive within Mode)
        for sm in ir_data.state_machines:
            mode_entity = sm["mode_entity"]
            modes_map = sm["modes_map"]
            
            current_mode = "always"
            if mode_entity:
                state = hass.states.get(mode_entity)
                if state:
                    current_mode = state.state
            
            # Check current mode, fallback to "always" if needed? 
            # Actually user wants "always" handled via global block now, but some might want per-SM always.
            # Let's support both current_mode and "always" within SM if they exist.
            for m in [current_mode, "always"]:
                if m in modes_map and code in modes_map[m]:
                    _LOGGER.debug("Matched SM Mode %s for %s", m, code)
                    await execute_actions(hass, ir_data, modes_map[m][code])
                    break # Next State Machine

    async def execute_actions(hass, ir_data, actions):
        for act_info in actions:
            if act_info["type"] == "service":
                act = act_info["action"]
                domain, service = act[CONF_SERVICE].split(".")
                await hass.services.async_call(domain, service, act.get(CONF_DATA, {}), target=act.get("target"), blocking=False)
            elif act_info["type"] == "transmit":
                act = act_info["action"]
                tx_id = act.get("transmitter")
                transmitter = ir_data.transmitters.get(tx_id)
                if transmitter:
                    await transmitter.async_send(act["code"], force_aeha_tx=act.get("force_aeha_tx", False))

    hass.bus.async_listen(EVENT_IR_RECEIVED, handle_ir_event)
    hass.async_create_task(hass.config_entries.flow.async_init(DOMAIN, context={"source": "import"}, data={}))
    return True

async def async_setup_entry(hass, entry):
    ir_data = hass.data[DOMAIN]
    await ir_data.async_register_devices(entry)
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button", "light", "switch", "media_player"])
    return True

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, ["sensor", "button", "light", "switch", "media_player"])
