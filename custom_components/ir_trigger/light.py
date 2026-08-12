import logging
from typing import ClassVar

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    ATTR_IS_ON,
    CONF_BUTTONS,
    CONF_DOMAIN,
    CONF_MAPPING,
    CONF_NAME,
    CONF_RECEIVER,
    CONF_STATE_SYNC,
    CONF_SYNC_PHYSICAL_CONTROLLER,
    CONF_TRANSMITTER,
    DOMAIN,
    SERVICE_SET_STATE,
    SIGNAL_IR_CODE_RECEIVED,
    SIGNAL_LOAD_COMPLETE,
)
from .entity import IRTriggerEntity
from .physical_sync import (
    apply_light_sync_action,
    build_light_sync_actions,
    validate_receiver_scope,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up the IR-Trigger light platform from a config entry."""
    ir_data = hass.data[DOMAIN]

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_STATE,
        {vol.Required(ATTR_IS_ON): cv.boolean},
        "async_sync_state",
    )

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
                    sync_physical_controller=device_info.get(
                        CONF_SYNC_PHYSICAL_CONTROLLER, False
                    ),
                    receivers=device_info.get(CONF_RECEIVER),
                    state_sync=device_info.get(CONF_STATE_SYNC, {}),
                )
            )

        async_add_entities(entities)

    if ir_data.loaded:
        await async_setup_lights()
    else:
        # One-shot: run once on first successful load, then disconnect.
        # Also disconnected on entry unload to avoid duplicate adds across reloads.
        unsub = None

        async def _async_setup_once():
            nonlocal unsub
            if unsub:
                unsub()
                unsub = None
            await async_setup_lights()

        unsub = async_dispatcher_connect(hass, SIGNAL_LOAD_COMPLETE, _async_setup_once)

        def _cleanup():
            nonlocal unsub
            if unsub:
                unsub()
                unsub = None

        entry.async_on_unload(_cleanup)

class IRTriggerLight(IRTriggerEntity, LightEntity):
    """Representation of an IR Trigger Light."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes: ClassVar[set[ColorMode]] = {ColorMode.ONOFF}

    def __init__(
        self,
        hass,
        device_id,
        device_name,
        transmitter,
        transmitter_id,
        buttons,
        mapping,
        *,
        sync_physical_controller,
        receivers,
        state_sync,
    ):
        """Initialize the light."""
        super().__init__(
            hass,
            device_id,
            device_name,
            transmitter,
            transmitter_id,
            buttons,
            mapping,
        )
        self._is_on = False
        self._attr_unique_id = f"ir_trigger_light_{self._device_id}"
        self._sync_physical_controller = sync_physical_controller
        self._sync_receivers = validate_receiver_scope(
            sync_physical_controller, receivers, device_id
        )
        self._physical_sync_actions = (
            build_light_sync_actions(buttons, mapping, state_sync)
            if sync_physical_controller
            else {}
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to accepted physical-controller frames when opted in."""
        await super().async_added_to_hass()
        if self._sync_physical_controller:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_IR_CODE_RECEIVED,
                    self._async_receive_ir_code,
                )
            )

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

    async def async_sync_state(self, is_on: bool) -> None:
        """Update the reported state to match an externally observed IR signal.

        Does not transmit — for reflecting state learned from a receiver
        (e.g. the physical remote was used) without re-sending IR.
        """
        self._is_on = is_on
        self.async_write_ha_state()

    @callback
    def _async_receive_ir_code(self, receiver: str, code: str) -> None:
        """Apply deterministic light state semantics without transmitting IR."""
        if receiver not in self._sync_receivers:
            return
        action = self._physical_sync_actions.get(code)
        if action is None:
            return
        state = apply_light_sync_action(self._is_on, action)
        if state is None:
            return
        self._is_on = state
        _LOGGER.info(
            "Synchronized light %s from receiver %s using %s",
            self._device_id,
            receiver,
            action,
        )
        self.async_write_ha_state()
