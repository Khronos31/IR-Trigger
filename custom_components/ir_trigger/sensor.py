import logging
from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SIGNAL_NEW_RECEIVER,
    SIGNAL_UPDATE_SENSOR,
    ATTR_CODE,
    ATTR_CONTROLLER,
    ATTR_BUTTON,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up the IR-Trigger sensor platform from a config entry."""
    _LOGGER.info("IR-Trigger sensor platform initialized")
    ir_data = hass.data[DOMAIN]
    
    async def async_add_receiver(receiver: str):
        """Add new sensors for a new receiver."""
        _LOGGER.info("Adding sensors for new receiver: %s", receiver)
        sensors = [
            IRTriggerSensor(receiver, ATTR_CODE, "Latest IR Signal", "mdi:remote"),
            IRTriggerSensor(receiver, ATTR_CONTROLLER, "Latest IR Controller", "mdi:gamepad-variant"),
            IRTriggerSensor(receiver, ATTR_BUTTON, "Latest IR Button", "mdi:radiobox-marked"),
        ]
        async_add_entities(sensors)

    # Listen for new receivers
    async_dispatcher_connect(hass, SIGNAL_NEW_RECEIVER, async_add_receiver)
    
    # If there are any known receivers (unlikely on startup, but just in case)
    for receiver in ir_data.known_receivers:
        await async_add_receiver(receiver)

class IRTriggerSensor(SensorEntity):
    """Representation of an IR Trigger Sensor."""

    def __init__(self, receiver: str, sensor_type: str, name_suffix: str, icon: str):
        """Initialize the sensor."""
        self._receiver = receiver
        self._sensor_type = sensor_type
        self._name_suffix = name_suffix
        self._icon = icon
        self._state = None
        self._attr_name = f"{receiver} {name_suffix}"
        self._attr_unique_id = f"ir_trigger_{receiver}_{sensor_type}"

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def device_info(self):
        """Return device information about this receiver."""
        return {
            "identifiers": {(DOMAIN, self._receiver)},
            "name": f"IR Receiver ({self._receiver})",
            "manufacturer": "IR-Trigger",
            "model": "Virtual IR Receiver",
        }

    async def async_added_to_hass(self):
        """Register callbacks."""
        
        async def async_update_state(receiver: str, sensor_data: dict):
            if receiver == self._receiver:
                new_state = sensor_data.get(self._sensor_type)
                if new_state is not None:
                    self._state = new_state
                    self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_UPDATE_SENSOR, async_update_state
            )
        )
