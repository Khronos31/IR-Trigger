import logging
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature, PRECISION_WHOLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    SIGNAL_LOAD_COMPLETE,
    CONF_NAME,
    CONF_TRANSMITTER,
    CONF_BUTTONS,
    CONF_DOMAIN,
    CONF_MAPPING,
)
from .entity import IRTriggerEntity

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
                    hvac_modes=hvac_modes,
                    fan_modes=device_info.get("fan_modes") or [],
                    preset_modes=device_info.get("preset_modes") or [],
                    min_temp=device_info.get("min_temp", 16),
                    max_temp=device_info.get("max_temp", 30),
                    default_fan_mode=device_info.get("default_fan_mode"),
                    default_temperature=float(device_info.get("default_temperature", 20)),
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
        hvac_modes,
        fan_modes,
        preset_modes,
        min_temp,
        max_temp,
        default_fan_mode,
        default_temperature,
    ):
        super().__init__(hass, device_id, device_name, transmitter, transmitter_id, buttons, mapping)
        self._attr_unique_id = f"ir_trigger_climate_{device_id}"
        self._encoder = encoder

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

    # ── Service handlers ─────────────────────────────────────────────────────

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._hvac_mode = hvac_mode
        await self._async_send_state()

    async def async_turn_on(self) -> None:
        # Resume with the first non-off, non-fan_only mode (usually "heat")
        for mode in self._attr_hvac_modes:
            if mode not in (HVACMode.OFF, HVACMode.FAN_ONLY):
                self._hvac_mode = mode
                break
        await self._async_send_state()

    async def async_turn_off(self) -> None:
        self._hvac_mode = HVACMode.OFF
        await self._async_send_state()

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get("temperature")
        if temp is None:
            return
        self._target_temperature = float(temp)
        if self._hvac_mode == HVACMode.OFF:
            self._hvac_mode = HVACMode.HEAT
        await self._async_send_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if self._attr_fan_modes and fan_mode not in self._attr_fan_modes:
            _LOGGER.warning("Unknown fan mode: %s", fan_mode)
            return
        self._fan_mode = fan_mode
        if self._hvac_mode == HVACMode.OFF:
            self._hvac_mode = HVACMode.HEAT
        await self._async_send_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if self._attr_preset_modes and preset_mode not in self._attr_preset_modes:
            _LOGGER.warning("Unknown preset mode: %s", preset_mode)
            return
        self._preset_mode = preset_mode
        await self._async_send_state()

    # ── IR transmission ──────────────────────────────────────────────────────

    async def _async_send_state(self) -> None:
        code = self._encoder(
            str(self._hvac_mode),
            self._fan_mode,
            self._target_temperature,
            self._preset_mode,
        )
        _LOGGER.info(
            "Sending climate IR: %s (hvac=%s fan=%s temp=%s preset=%s)",
            code, self._hvac_mode, self._fan_mode, self._target_temperature, self._preset_mode,
        )
        if self._transmitter:
            await self._transmitter.async_send(code)
        self.async_write_ha_state()
