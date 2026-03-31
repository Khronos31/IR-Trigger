import logging
from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    SIGNAL_LOAD_COMPLETE,
    CONF_NAME,
    CONF_TRANSMITTER,
    CONF_BUTTONS,
    CONF_FORCE_AEHA_TX,
    CONF_DOMAIN,
    CONF_MAPPING,
)
from .entity import IRTriggerEntity

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

            tx_id = device_info.get(CONF_TRANSMITTER)
            if not tx_id:
                # Silently skip devices without a transmitter (e.g., remotes)
                continue

            tx = ir_data.transmitters.get(tx_id)
            if not tx:
                _LOGGER.warning("Transmitter %s not found for light %s", tx_id, device_id)
                continue
                
            entities.append(
                IRTriggerLight(
                    hass,
                    device_id,
                    device_info.get(CONF_NAME, device_id),
                    tx,
                    tx_id,
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

class IRTriggerLight(IRTriggerEntity, LightEntity):
    """Representation of an IR Trigger Light."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, *args, **kwargs):
        """Initialize the light."""
        super().__init__(*args, **kwargs)
        self._is_on = False
        self._attr_unique_id = f"ir_trigger_light_{self._device_id}"

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        return self._is_on

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
