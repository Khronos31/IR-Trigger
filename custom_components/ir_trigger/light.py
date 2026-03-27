import logging
from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    ATTR_VIA_DEVICE,
    SIGNAL_LOAD_COMPLETE,
    CONF_NAME,
    CONF_TRANSMITTER,
    CONF_BUTTONS,
    CONF_FORCE_AEHA_TX,
    CONF_DOMAIN,
    CONF_MAPPING,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up the IR-Trigger light platform from a config entry."""
    ir_data = hass.data[DOMAIN]
    
    async def async_setup_lights():
        """Create lights for mapped devices."""
        entities = []
        for device_id, device_info in ir_data.devices.items():
            if device_info.get(CONF_DOMAIN) != "light":
                continue

            transmitter_id = device_info.get(CONF_TRANSMITTER)
            transmitter = ir_data.transmitters.get(transmitter_id)
            if not transmitter:
                _LOGGER.warning("Transmitter %s not found for light %s", transmitter_id, device_id)
                continue
                
            entities.append(
                IRTriggerLight(
                    hass,
                    device_id,
                    device_info.get(CONF_NAME, device_id),
                    transmitter,
                    transmitter_id,
                    device_info.get(CONF_BUTTONS, {}),
                    device_info.get(CONF_MAPPING, {}),
                    device_info.get(CONF_FORCE_AEHA_TX, False)
                )
            )
        
        async_add_entities(entities)

    if ir_data.loaded:
        await async_setup_lights()
    else:
        async_dispatcher_connect(hass, SIGNAL_LOAD_COMPLETE, async_setup_lights)

class IRTriggerLight(LightEntity):
    """Representation of an IR Trigger Light."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, hass, device_id, device_name, transmitter, transmitter_id, buttons, mapping, force_aeha_tx):
        """Initialize the light."""
        self.hass = hass
        self._device_id = device_id
        self._device_name = device_name
        self._transmitter = transmitter
        self._transmitter_id = transmitter_id
        self._buttons = buttons
        self._mapping = mapping
        self._force_aeha_tx = force_aeha_tx
        
        self._is_on = False
        self._attr_name = device_name
        self._attr_unique_id = f"ir_trigger_light_{device_id}"

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._is_on

    async def _async_send_mapped_button(self, mapping_key):
        """Send IR code for the mapped button."""
        button_key = self._mapping.get(mapping_key)
        if not button_key:
            _LOGGER.debug("No mapping for %s on device %s", mapping_key, self._device_id)
            return False
            
        ir_code = self._buttons.get(button_key)
        if not ir_code:
            _LOGGER.warning("Button key %s not found in buttons for device %s", button_key, self._device_id)
            return False
            
        await self._transmitter.async_send(ir_code, force_aeha_tx=self._force_aeha_tx)
        return True

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        if await self._async_send_mapped_button("turn_on"):
            self._is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        if await self._async_send_mapped_button("turn_off"):
            self._is_on = False
            self.async_write_ha_state()

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "IR-Trigger",
            "model": "Target Device (Light)",
            ATTR_VIA_DEVICE: (DOMAIN, self._transmitter_id),
        }
