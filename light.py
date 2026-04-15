import logging

from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.helpers.restore_state import RestoreEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass,
    entry,
    async_add_entities,
    discovery_info=None,
):
    """Set up BuildTrack lights."""
    data = hass.data[DOMAIN][entry.entry_id]
    devices = data["devices"]
    api = data["api"]

    lights = []
    _LOGGER.info("somnath : %s", devices)
    for device in devices:
        if "LIGHT" in device.get("type", []):
            lights.append(BuildTrackLight(hass, api, device))
        elif "LIGHT DIMMER" in device.get("type", []):
            lights.append(BuildTrackDimmer(hass, api, device))
    async_add_entities(lights)


class BuildTrackLight(LightEntity):

    def __init__(self, hass, api, device):
        """Initialize the light entity."""
        self._hass = hass
        self._api = api
        self._device = device

        self._entity_id = device.get("entityId")
        self._entity_key = device.get("entityKey")

        self._attr_name = device.get("entityName")
        self._attr_unique_id = self._entity_id

        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._attr_color_mode = ColorMode.ONOFF
        self._attr_is_on = False

    # -------------------------------------------------
    # INTERNAL POWER HANDLER
    # -------------------------------------------------

    async def _async_set_power(self, state: str, is_on: bool):
        """Internal power handler."""

        response = await self._api.call(
            endpoint=f"/controlDevice/{self._entity_id}",
            method="POST",
            payload={
                "entityId": self._entity_id,
                "entityKey": self._entity_key,
                "state": state,
            },
        )

        if response is not None:
            self._attr_is_on = is_on
            self.async_write_ha_state()

    # -------------------------------------------------
    # TURN ON
    # -------------------------------------------------

    async def async_turn_on(self, **kwargs):
        """Turn the light on."""
        await self._async_set_power("on", True)

    # -------------------------------------------------
    # TURN OFF
    # -------------------------------------------------

    async def async_turn_off(self, **kwargs):
        """Turn the light off."""
        await self._async_set_power("off", False)



class BuildTrackDimmer(LightEntity, RestoreEntity):

    def __init__(self, hass, api, device):
        self._api = api

        self._entity_id = device.get("entityId")   # REQUIRED for endpoint
        self._entity_key = device.get("entityKey")

        self._attr_name = device.get("entityName")
        self._attr_unique_id = self._entity_id

        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._attr_color_mode = ColorMode.BRIGHTNESS

        self._attr_is_on = False
        self._attr_brightness = 128

    # -------------------------------------------------
    # REQUIRED PROPERTIES
    # -------------------------------------------------
    @property
    def is_on(self):
        return self._attr_is_on

    @property
    def brightness(self):
        return self._attr_brightness

    @property
    def available(self):
        return True

    # -------------------------------------------------
    # RESTORE STATE
    # -------------------------------------------------
    async def async_added_to_hass(self):
        last_state = await self.async_get_last_state()

        if last_state:
            self._attr_is_on = last_state.state == "on"

            if "brightness" in last_state.attributes:
                self._attr_brightness = last_state.attributes["brightness"]

    # -------------------------------------------------
    # INTERNAL CONTROL FUNCTION
    # -------------------------------------------------
    async def _async_set_power(self, state: str, brightness_percent: int):

        response = await self._api.call(
            endpoint=f"/controlDevice/{self._entity_id}",
            method="POST",
            payload={
                "entityId": self._entity_id,
                "entityKey": self._entity_key,
                "state": state,
                "speed": brightness_percent,  # add brightness for dimmer
            },
        )

        if response is not None:
            self._attr_is_on = state.lower() == "on"
            self.async_write_ha_state()

    # -------------------------------------------------
    # TURN ON
    # -------------------------------------------------
    async def async_turn_on(self, **kwargs):

        brightness = kwargs.get("brightness")

        if brightness is not None:
            self._attr_brightness = brightness

        if self._attr_brightness is None:
            self._attr_brightness = 255  # default full brightness

        brightness_percent = int((self._attr_brightness / 255) * 100)

        await self._async_set_power("on", brightness_percent)

    # -------------------------------------------------
    # TURN OFF
    # -------------------------------------------------
    async def async_turn_off(self, **kwargs):

        await self._async_set_power("off", 0)
