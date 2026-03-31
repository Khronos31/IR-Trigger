import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    ATTR_VIA_DEVICE,
    SIGNAL_LOAD_COMPLETE,
    CONF_NAME,
    CONF_HUB,
    CONF_BUTTONS,
    CONF_FORCE_AEHA_TX,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up the IR-Trigger button platform from a config entry."""
    ir_data = hass.data[DOMAIN]
    
    async def async_setup_buttons():
        """Create buttons for all devices."""
        entities = []
        for device_id, device_info in ir_data.devices.items():
            hub_id = device_info.get(CONF_HUB)
            if not hub_id:
                # Silently skip devices without a hub (e.g., remotes)
                continue

            hub = ir_data.hubs.get(hub_id)
            if not hub:
                _LOGGER.warning("Hub %s not found for device %s", hub_id, device_id)
                continue
                
            for button_name, ir_code in device_info.get(CONF_BUTTONS, {}).items():
                entities.append(
                    IRTriggerButton(
                        hass,
                        device_id,
                        device_info.get(CONF_NAME, device_id),
                        button_name,
                        ir_code,
                        hub,
                        hub_id,
                        device_info.get(CONF_FORCE_AEHA_TX, False)
                    )
                )
        
        async_add_entities(entities)

    # If data is already loaded, setup buttons now
    if ir_data.loaded:
        await async_setup_buttons()
    else:
        # Otherwise wait for the signal
        async_dispatcher_connect(hass, SIGNAL_LOAD_COMPLETE, async_setup_buttons)

class IRTriggerButton(ButtonEntity):
    """Representation of an IR Trigger Button."""

    def __init__(self, hass, device_id, device_name, button_name, ir_code, hub, hub_id, force_aeha_tx):
        """Initialize the button."""
        self.hass = hass
        self._device_id = device_id
        self._device_name = device_name
        self._button_name = button_name
        self._ir_code = ir_code
        self._hub = hub
        self._hub_id = hub_id
        self._force_aeha_tx = force_aeha_tx
        
        self._attr_name = f"{device_name} {button_name}"
        self._attr_unique_id = f"ir_trigger_btn_{device_id}_{button_name}"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Button pressed: %s (%s)", self._attr_name, self._ir_code)
        if self._hub:
            await self._hub.async_send(self._ir_code, force_aeha_tx=self._force_aeha_tx)

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "IR-Trigger",
            "model": "Target Device",
            ATTR_VIA_DEVICE: (DOMAIN, self._hub_id),
        }
