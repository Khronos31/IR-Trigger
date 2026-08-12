import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    ATTR_VIA_DEVICE,
    CONF_BUTTONS,
    CONF_DOMAIN,
    CONF_NAME,
    CONF_TRANSMITTER,
    DOMAIN,
    SIGNAL_LOAD_COMPLETE,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up the IR-Trigger button platform from a config entry."""
    ir_data = hass.data[DOMAIN]
    
    async def async_setup_buttons():
        """Create buttons for all devices."""
        entities = []
        for device_id, device_info in ir_data.devices.items():
            tx_id = device_info.get(CONF_TRANSMITTER)
            if not tx_id:
                # Silently skip devices without a transmitter (e.g., remotes)
                continue

            tx = ir_data.transmitters.get(tx_id)
            if not tx:
                _LOGGER.warning("Transmitter %s not found for device %s", tx_id, device_id)
                continue
                
            for button_name, ir_code in device_info.get(CONF_BUTTONS, {}).items():
                entities.append(
                    IRTriggerButton(
                        hass,
                        device_id,
                        device_info.get(CONF_NAME, device_id),
                        button_name,
                        ir_code,
                        tx,
                        tx_id
                    )
                )

            if device_info.get(CONF_DOMAIN) == "climate":
                for button_name, action in device_info.get("climate_buttons", {}).items():
                    entities.append(
                        IRTriggerClimateCommandButton(
                            hass,
                            device_id,
                            device_info.get(CONF_NAME, device_id),
                            button_name,
                            action,
                            ir_data,
                            tx_id,
                        )
                    )
        
        async_add_entities(entities)

    # If data is already loaded, setup buttons now
    if ir_data.loaded:
        await async_setup_buttons()
    else:
        # One-shot: run once on first successful load, then disconnect.
        # Also disconnected on entry unload to avoid duplicate adds across reloads.
        unsub = None

        async def _async_setup_once():
            nonlocal unsub
            if unsub:
                unsub()
                unsub = None
            await async_setup_buttons()

        unsub = async_dispatcher_connect(hass, SIGNAL_LOAD_COMPLETE, _async_setup_once)

        def _cleanup():
            nonlocal unsub
            if unsub:
                unsub()
                unsub = None

        entry.async_on_unload(_cleanup)

class IRTriggerButton(ButtonEntity):
    """Representation of an IR Trigger Button."""

    def __init__(self, hass, device_id, device_name, button_name, ir_code, transmitter, transmitter_id):
        """Initialize the button."""
        self.hass = hass
        self._device_id = device_id
        self._device_name = device_name
        self._button_name = button_name
        self._ir_code = ir_code
        self._transmitter = transmitter
        self._transmitter_id = transmitter_id
        
        self._attr_name = f"{device_name} {button_name}"
        self._attr_unique_id = f"ir_trigger_btn_{device_id}_{button_name}"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Button pressed: %s (%s)", self._attr_name, self._ir_code)
        if self._transmitter:
            await self._transmitter.async_send(self._ir_code)

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


class IRTriggerClimateCommandButton(ButtonEntity):
    """A button whose frame is generated from the climate's current state."""

    def __init__(self, hass, device_id, device_name, button_name, action, ir_data, transmitter_id):
        self.hass = hass
        self._device_id = device_id
        self._device_name = device_name
        self._button_name = button_name
        self._action = action
        self._ir_data = ir_data
        self._transmitter_id = transmitter_id
        self._attr_name = f"{device_name} {button_name}"
        self._attr_unique_id = f"ir_trigger_climate_btn_{device_id}_{action}"

    async def async_press(self) -> None:
        climate = self._ir_data.climate_entities.get(self._device_id)
        if climate is None:
            _LOGGER.warning("Climate entity %s is not available", self._device_id)
            return
        await climate.async_send_protocol_command(self._action)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "IR-Trigger",
            "model": "Target Device",
            ATTR_VIA_DEVICE: (DOMAIN, f"tx_{self._transmitter_id}"),
        }
