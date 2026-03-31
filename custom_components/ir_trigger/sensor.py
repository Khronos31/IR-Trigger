import logging
from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SIGNAL_UPDATE_SENSOR,
    ATTR_CODE,
    ATTR_DEVICE,
    ATTR_BUTTON,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up the IR-Trigger sensor platform from a config entry."""
    _LOGGER.info("IR-Trigger sensor platform initialized")
    ir_data = hass.data[DOMAIN]
    
    sensors = []
    for hub_id, hub in ir_data.hubs.items():
        if hub.rx:
            _LOGGER.info("Adding sensors for RX Hub: %s", hub_id)
            sensors.extend([
                IRTriggerSensor(hub_id, ATTR_CODE, "Latest IR Signal", "mdi:remote"),
                IRTriggerSensor(hub_id, ATTR_DEVICE, "Latest IR Device", "mdi:gamepad-variant"),
                IRTriggerSensor(hub_id, ATTR_BUTTON, "Latest IR Button", "mdi:radiobox-marked"),
            ])
    
    if sensors:
        async_add_entities(sensors)

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
        """Return device information about this hub."""
        return {
            "identifiers": {(DOMAIN, self._receiver)},
            "name": f"IR Hub ({self._receiver})",
            "manufacturer": "IR-Trigger",
            "model": "IR-Hub",
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
