import logging
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerDeviceClass,
    MediaType,
)
from homeassistant.components.media_player.const import MediaPlayerState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    ATTR_VIA_DEVICE,
    SIGNAL_LOAD_COMPLETE,
    CONF_NAME,
    CONF_TRANSMITTER,
    CONF_BUTTONS,
    CONF_FORCE_AEHA_TX,
    CONF_DOMAIN,
    CONF_MAPPING,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up the IR-Trigger media_player platform from a config entry."""
    ir_data = hass.data[DOMAIN]
    
    async def async_setup_media_players():
        """Create media players for mapped devices."""
        entities = []
        for device_id, device_info in ir_data.devices.items():
            if device_info.get(CONF_DOMAIN) != "media_player":
                continue

            transmitter_id = device_info.get(CONF_TRANSMITTER)
            transmitter = ir_data.transmitters.get(transmitter_id)
            if not transmitter:
                _LOGGER.warning("Transmitter %s not found for media_player %s", transmitter_id, device_id)
                continue
                
            entities.append(
                IRTriggerMediaPlayer(
                    hass,
                    device_id,
                    device_info.get(CONF_NAME, device_id),
                    transmitter,
                    transmitter_id,
                    device_info.get(CONF_BUTTONS, {}),
                    device_info.get(CONF_MAPPING, {}),
                    device_info.get(CONF_FORCE_AEHA_TX, False)
                )
            )
        
        async_add_entities(entities)

    if ir_data.loaded:
        await async_setup_media_players()
    else:
        async_dispatcher_connect(hass, SIGNAL_LOAD_COMPLETE, async_setup_media_players)

class IRTriggerMediaPlayer(MediaPlayerEntity):
    """Representation of an IR Trigger Media Player."""

    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_media_content_type = MediaType.VIDEO

    def __init__(self, hass, device_id, device_name, transmitter, transmitter_id, buttons, mapping, force_aeha_tx):
        """Initialize the media player."""
        self.hass = hass
        self._device_id = device_id
        self._device_name = device_name
        self._transmitter = transmitter
        self._transmitter_id = transmitter_id
        self._buttons = buttons
        self._mapping = mapping
        self._force_aeha_tx = force_aeha_tx
        
        self._state = MediaPlayerState.OFF
        self._attr_name = device_name
        self._attr_unique_id = f"ir_trigger_media_player_{device_id}"
        
        # Supported features based on mapping
        self._attr_supported_features = MediaPlayerEntityFeature(0)
        if "turn_on" in mapping:
            self._attr_supported_features |= MediaPlayerEntityFeature.TURN_ON
        if "turn_off" in mapping:
            self._attr_supported_features |= MediaPlayerEntityFeature.TURN_OFF
        if "volume_up" in mapping or "volume_down" in mapping:
            self._attr_supported_features |= MediaPlayerEntityFeature.VOLUME_STEP
        if "volume_mute" in mapping:
            self._attr_supported_features |= MediaPlayerEntityFeature.VOLUME_MUTE
        if "play" in mapping:
            self._attr_supported_features |= MediaPlayerEntityFeature.PLAY
        if "pause" in mapping:
            self._attr_supported_features |= MediaPlayerEntityFeature.PAUSE
        if "stop" in mapping:
            self._attr_supported_features |= MediaPlayerEntityFeature.STOP
        if "next_track" in mapping:
            self._attr_supported_features |= MediaPlayerEntityFeature.NEXT_TRACK
        if "previous_track" in mapping:
            self._attr_supported_features |= MediaPlayerEntityFeature.PREVIOUS_TRACK

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the player."""
        return self._state

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
            
        await self._transmitter.async_send(ir_code, force_aeha_tx=self._force_aeha_tx)
        return True

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        if await self._async_send_mapped_button("turn_on"):
            self._state = MediaPlayerState.ON
            self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        if await self._async_send_mapped_button("turn_off"):
            self._state = MediaPlayerState.OFF
            self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        """Volume up the media player."""
        await self._async_send_mapped_button("volume_up")

    async def async_volume_down(self) -> None:
        """Volume down the media player."""
        await self._async_send_mapped_button("volume_down")

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        await self._async_send_mapped_button("volume_mute")

    async def async_media_play(self) -> None:
        """Send play command."""
        if await self._async_send_mapped_button("play"):
            self._state = MediaPlayerState.PLAYING
            self.async_write_ha_state()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        if await self._async_send_mapped_button("pause"):
            self._state = MediaPlayerState.PAUSED
            self.async_write_ha_state()

    async def async_media_stop(self) -> None:
        """Send stop command."""
        if await self._async_send_mapped_button("stop"):
            self._state = MediaPlayerState.IDLE
            self.async_write_ha_state()

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        await self._async_send_mapped_button("next_track")

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        await self._async_send_mapped_button("previous_track")

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "IR-Trigger",
            "model": "Target Device (MediaPlayer)",
            ATTR_VIA_DEVICE: (DOMAIN, self._transmitter_id),
        }
