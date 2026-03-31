import logging
from homeassistant.components.switch import SwitchEntity
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
    """Set up the IR-Trigger switch platform from a config entry."""
    ir_data = hass.data[DOMAIN]
    
    async def async_setup_switches():
        """Create switches for mapped devices."""
        entities = []
        for device_id, device_info in ir_data.devices.items():
            if device_info.get(CONF_DOMAIN) != "switch":
                continue

            tx_id = device_info.get(CONF_TRANSMITTER)
            if not tx_id:
                # Silently skip devices without a transmitter (e.g., remotes)
                continue

            tx = ir_data.transmitters.get(tx_id)
            if not tx:
                _LOGGER.warning("Transmitter %s not found for switch %s", tx_id, device_id)
                continue
                
            entities.append(
                IRTriggerSwitch(
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
        await async_setup_switches()
    else:
        async_dispatcher_connect(hass, SIGNAL_LOAD_COMPLETE, async_setup_switches)

class IRTriggerSwitch(IRTriggerEntity, SwitchEntity):
    """Representation of an IR Trigger Switch."""

    def __init__(self, *args, **kwargs):
        """Initialize the switch."""
        super().__init__(*args, **kwargs)
        self._is_on = False
        self._attr_unique_id = f"ir_trigger_switch_{self._device_id}"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        if await self._async_send_mapped_button("turn_on"):
            self._is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        if await self._async_send_mapped_button("turn_off"):
            self._is_on = False
            self.async_write_ha_state()
