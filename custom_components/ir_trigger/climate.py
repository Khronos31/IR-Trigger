import inspect
import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    CONF_BUTTONS,
    CONF_DOMAIN,
    CONF_MAPPING,
    CONF_NAME,
    CONF_RECEIVER,
    CONF_SYNC_PHYSICAL_CONTROLLER,
    CONF_TRANSMITTER,
    DOMAIN,
    SIGNAL_IR_CODE_RECEIVED,
    SIGNAL_LOAD_COMPLETE,
)
from .entity import IRTriggerEntity
from .physical_sync import validate_receiver_scope

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    ir_data = hass.data[DOMAIN]

    async def async_setup_climates():
        entities = []
        for device_id, device_info in ir_data.devices.items():
            if device_info.get(CONF_DOMAIN) != "climate":
                continue

            tx_id = device_info.get(CONF_TRANSMITTER)
            if not tx_id:
                continue

            tx = ir_data.transmitters.get(tx_id)
            if not tx:
                _LOGGER.warning("Transmitter %s not found for climate %s", tx_id, device_id)
                continue

            encoder = device_info.get("_encode")
            if not encoder:
                _LOGGER.warning(
                    "Climate device %s has no encoder — add a Python template with an encode() function",
                    device_id,
                )
                continue

            try:
                hvac_modes = [HVACMode(m) for m in device_info.get("hvac_modes", ["heat", "off"])]
            except ValueError as e:
                _LOGGER.error("Invalid hvac_mode in template for %s: %s", device_id, e)
                continue

            entities.append(
                IRTriggerClimate(
                    hass,
                    device_id,
                    device_info.get(CONF_NAME, device_id),
                    tx,
                    tx_id,
                    device_info.get(CONF_BUTTONS, {}),
                    device_info.get(CONF_MAPPING, {}),
                    encoder=encoder,
                    decoder=device_info.get("_decode"),
                    hvac_modes=hvac_modes,
                    fan_modes=device_info.get("fan_modes") or [],
                    preset_modes=device_info.get("preset_modes") or [],
                    min_temp=device_info.get("min_temp", 16),
                    max_temp=device_info.get("max_temp", 30),
                    default_fan_mode=device_info.get("default_fan_mode"),
                    default_temperature=float(device_info.get("default_temperature", 20)),
                    default_temperatures=device_info.get("default_temperatures") or {},
                    temperature_ranges=device_info.get("temperature_ranges") or {},
                    climate_buttons=device_info.get("climate_buttons") or {},
                    climate_button_states=device_info.get("climate_button_states") or {},
                    preset_start_modes=device_info.get("preset_start_modes") or {},
                    clear_eco_on_hvac_mode=device_info.get(
                        "clear_eco_on_hvac_mode", False
                    ),
                    sync_physical_controller=device_info.get(
                        CONF_SYNC_PHYSICAL_CONTROLLER, False
                    ),
                    receivers=device_info.get(CONF_RECEIVER),
                )
            )

        async_add_entities(entities)

    if ir_data.loaded:
        await async_setup_climates()
    else:
        unsub = None

        async def _async_setup_once():
            nonlocal unsub
            if unsub:
                unsub()
                unsub = None
            await async_setup_climates()

        unsub = async_dispatcher_connect(hass, SIGNAL_LOAD_COMPLETE, _async_setup_once)

        def _cleanup():
            nonlocal unsub
            if unsub:
                unsub()
                unsub = None

        entry.async_on_unload(_cleanup)


class IRTriggerClimate(IRTriggerEntity, ClimateEntity):
    """Generic IR-controlled climate entity driven by a Python template encoder."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = PRECISION_WHOLE

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
        encoder,
        decoder,
        hvac_modes,
        fan_modes,
        preset_modes,
        min_temp,
        max_temp,
        default_fan_mode,
        default_temperature,
        default_temperatures,
        temperature_ranges,
        climate_buttons,
        climate_button_states,
        preset_start_modes,
        clear_eco_on_hvac_mode,
        sync_physical_controller,
        receivers,
    ):
        super().__init__(hass, device_id, device_name, transmitter, transmitter_id, buttons, mapping)
        self._attr_unique_id = f"ir_trigger_climate_{device_id}"
        self._encoder = encoder
        self._decoder = decoder
        parameters = inspect.signature(encoder).parameters
        self._encoder_accepts_action = "action" in parameters
        self._encoder_accepts_protocol_mode = "protocol_mode" in parameters
        self._climate_buttons = climate_buttons
        self._climate_button_states = climate_button_states
        self._preset_start_modes = preset_start_modes
        self._clear_eco_on_hvac_mode = clear_eco_on_hvac_mode
        self._sync_physical_controller = sync_physical_controller
        self._receivers = validate_receiver_scope(
            sync_physical_controller, receivers, device_id
        )
        self._temperature_ranges = temperature_ranges
        self._default_temperatures = default_temperatures

        self._attr_hvac_modes = hvac_modes
        self._attr_fan_modes = fan_modes or None
        self._attr_preset_modes = preset_modes or None
        self._attr_min_temp = min_temp
        self._attr_max_temp = max_temp

        features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        if fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
        if preset_modes:
            features |= ClimateEntityFeature.PRESET_MODE
        self._attr_supported_features = features

        self._hvac_mode: HVACMode = HVACMode.OFF
        self._fan_mode: str | None = default_fan_mode or (fan_modes[0] if fan_modes else None)
        self._target_temperature: float = default_temperature
        self._preset_mode: str | None = preset_modes[0] if preset_modes else None
        self._protocol_mode: str = next(
            (str(mode) for mode in hvac_modes if mode != HVACMode.OFF),
            "off",
        )
        self._apply_temperature_limits(self._protocol_mode)

    async def async_added_to_hass(self) -> None:
        """Register this climate for dynamic command buttons and IR updates."""
        await super().async_added_to_hass()
        ir_data = self.hass.data[DOMAIN]
        ir_data.climate_entities[self._device_id] = self
        if self._sync_physical_controller:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_IR_CODE_RECEIVED,
                    self._async_receive_ir_code,
                )
            )

    async def async_will_remove_from_hass(self) -> None:
        """Remove the dynamic-button registry entry."""
        ir_data = self.hass.data[DOMAIN]
        if ir_data.climate_entities.get(self._device_id) is self:
            ir_data.climate_entities.pop(self._device_id, None)
        await super().async_will_remove_from_hass()

    # ── HA state properties ──────────────────────────────────────────────────

    @property
    def hvac_mode(self) -> HVACMode:
        return self._hvac_mode

    @property
    def fan_mode(self) -> str | None:
        return self._fan_mode

    @property
    def target_temperature(self) -> float:
        return self._target_temperature

    @property
    def preset_mode(self) -> str | None:
        return self._preset_mode

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the native protocol mode when HA has no exact equivalent."""
        return {"ir_protocol_mode": self._protocol_mode}

    # ── Service handlers ─────────────────────────────────────────────────────

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        previous_mode = self._protocol_mode
        self._hvac_mode = hvac_mode
        if hvac_mode != HVACMode.OFF:
            self._protocol_mode = str(hvac_mode)
            if self._clear_eco_on_hvac_mode:
                self._preset_mode = {
                    "eco": "normal",
                    "eco_save": "save",
                }.get(self._preset_mode, self._preset_mode)
            if str(hvac_mode) != previous_mode:
                self._target_temperature = float(
                    self._default_temperatures.get(str(hvac_mode), self._target_temperature)
                )
        self._apply_temperature_limits(self._protocol_mode)
        await self._async_send_state("turn_off" if hvac_mode == HVACMode.OFF else "set_hvac_mode")

    async def async_turn_on(self) -> None:
        self._resume_hvac_mode()
        self._apply_temperature_limits(self._protocol_mode)
        await self._async_send_state("turn_on")

    async def async_turn_off(self) -> None:
        self._hvac_mode = HVACMode.OFF
        await self._async_send_state("turn_off")

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get("temperature")
        if temp is None:
            return
        previous = self._target_temperature
        was_off = self._hvac_mode == HVACMode.OFF
        self._target_temperature = float(temp)
        if was_off:
            self._resume_hvac_mode()
        if self._target_temperature == previous:
            if was_off:
                await self._async_send_state("turn_on")
            return
        action = "temperature_up" if self._target_temperature > previous else "temperature_down"
        await self._async_send_state(action)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if self._attr_fan_modes and fan_mode not in self._attr_fan_modes:
            _LOGGER.warning("Unknown fan mode: %s", fan_mode)
            return
        self._fan_mode = fan_mode
        if self._hvac_mode == HVACMode.OFF:
            self._resume_hvac_mode()
        await self._async_send_state("set_fan_mode")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if self._attr_preset_modes and preset_mode not in self._attr_preset_modes:
            _LOGGER.warning("Unknown preset mode: %s", preset_mode)
            return
        previous = self._preset_mode
        self._preset_mode = preset_mode
        if self._hvac_mode == HVACMode.OFF and preset_mode in self._preset_start_modes:
            start_mode = self._preset_start_modes[preset_mode]
            self._hvac_mode = HVACMode(start_mode)
            self._protocol_mode = start_mode
            self._target_temperature = float(
                self._default_temperatures.get(start_mode, self._target_temperature)
            )
            self._apply_temperature_limits(self._protocol_mode)
        old_eco = previous in ("eco", "eco_save")
        new_eco = preset_mode in ("eco", "eco_save")
        action = "set_eco" if old_eco != new_eco else "set_save"
        await self._async_send_state(action)

    async def async_send_protocol_command(self, action: str) -> bool:
        """Send a state-preserving template-defined companion command."""
        if action not in self._climate_buttons.values():
            _LOGGER.warning("Unknown climate command %s for %s", action, self._device_id)
            return False
        state = self._climate_button_states.get(action, {})
        if "hvac_mode" in state:
            self._hvac_mode = HVACMode(state["hvac_mode"])
        if "protocol_mode" in state:
            self._protocol_mode = state["protocol_mode"]
        if "fan_mode" in state:
            self._fan_mode = state["fan_mode"]
        if "temperature" in state:
            self._target_temperature = float(state["temperature"])
        if "preset_mode" in state:
            self._preset_mode = state["preset_mode"]
        self._apply_temperature_limits(self._protocol_mode)
        await self._async_send_state(action)
        return True

    # ── IR transmission ──────────────────────────────────────────────────────

    async def _async_send_state(self, action: str | None = None) -> None:
        args = (
            str(self._hvac_mode),
            self._fan_mode,
            self._target_temperature,
            self._preset_mode,
        )
        kwargs = {}
        if self._encoder_accepts_action:
            kwargs["action"] = action
        if self._encoder_accepts_protocol_mode:
            kwargs["protocol_mode"] = self._protocol_mode
        code = self._encoder(*args, **kwargs)
        _LOGGER.info(
            "Sending climate IR: %s (hvac=%s fan=%s temp=%s preset=%s action=%s)",
            code, self._hvac_mode, self._fan_mode, self._target_temperature,
            self._preset_mode, action,
        )
        if self._transmitter:
            await self._transmitter.async_send(code)
        self.async_write_ha_state()

    def _apply_temperature_limits(self, protocol_mode: str) -> None:
        limits = self._temperature_ranges.get(protocol_mode)
        if limits and len(limits) == 2:
            self._attr_min_temp = float(limits[0])
            self._attr_max_temp = float(limits[1])

    def _resume_hvac_mode(self) -> None:
        """Resume the protocol's retained mode, falling back to the first active mode."""
        try:
            retained = HVACMode(self._protocol_mode)
        except ValueError:
            retained = None
        if retained in self._attr_hvac_modes and retained != HVACMode.OFF:
            self._hvac_mode = retained
            return
        for mode in self._attr_hvac_modes:
            if mode not in (HVACMode.OFF, HVACMode.FAN_ONLY):
                self._hvac_mode = mode
                self._protocol_mode = str(mode)
                self._target_temperature = float(
                    self._default_temperatures.get(str(mode), self._target_temperature)
                )
                return

    @callback
    def _async_receive_ir_code(self, receiver: str, code: str) -> None:
        """Apply a decoded physical-remote frame without transmitting IR."""
        if (
            not self._sync_physical_controller
            or not self._decoder
            or receiver not in self._receivers
        ):
            return
        try:
            state = self._decoder(code)
        except Exception:
            _LOGGER.exception("Climate decoder failed for %s", self._device_id)
            return
        if not state:
            return
        try:
            self._hvac_mode = HVACMode(state["hvac_mode"])
        except (KeyError, ValueError):
            _LOGGER.warning("Climate decoder returned invalid HVAC state: %s", state)
            return
        if state.get("fan_mode") in (self._attr_fan_modes or []):
            self._fan_mode = state["fan_mode"]
        if state.get("temperature") is not None:
            self._target_temperature = float(state["temperature"])
        if state.get("preset_mode") in (self._attr_preset_modes or []):
            self._preset_mode = state["preset_mode"]
        self._protocol_mode = state.get("protocol_mode") or str(self._hvac_mode)
        self._apply_temperature_limits(self._protocol_mode)
        _LOGGER.info(
            "Synchronized climate %s from receiver %s: %s",
            self._device_id,
            receiver,
            state,
        )
        self.async_write_ha_state()
