import logging
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, ATTR_VIA_DEVICE

_LOGGER = logging.getLogger(__name__)

class IRTriggerEntity(Entity):
    """Base class for IR Trigger entities (Light, Switch, MediaPlayer)."""

    def __init__(self, hass, device_id, device_name, transmitter, transmitter_id, buttons, mapping):
        """Initialize the entity."""
        self.hass = hass
        self._device_id = device_id
        self._device_name = device_name
        self._transmitter = transmitter
        self._transmitter_id = transmitter_id
        self._buttons = buttons
        self._mapping = mapping
        
        self._attr_name = device_name

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
            
        if self._transmitter:
            await self._transmitter.async_send(ir_code)
            return True
        return False

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "IR-Trigger",
            "model": "Target Device",
            ATTR_VIA_DEVICE: (DOMAIN, f"tx_{self._transmitter_id}"),
        }
