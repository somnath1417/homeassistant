import logging

from datetime import timedelta

from homeassistant.components.light import (
    LightEntity,
    ColorMode,
)
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=5)


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
        await self._async_set_power("on", True)

    # -------------------------------------------------
    # TURN OFF
    # -------------------------------------------------

    async def async_turn_off(self, **kwargs):
        await self._async_set_power("off", False)

    # -------------------------------------------------
    # REALTIME UPDATE
    # -------------------------------------------------

    async def async_update(self):
        """Realtime state update from BuildTrack."""

        data = await self._api.call(
            endpoint="/readDeviceData",
            method="POST",
            payload={
                "entityId": self._entity_id,
                "entityKey": self._entity_key,
            },
        )

        _LOGGER.warning(
            "Realtime Light Data | %s | %s",
            self._attr_name,
            data,
        )

        if not data:
            return

        state = str(data.get("state", "")).lower()

        self._attr_is_on = state == "on"

        self.async_write_ha_state()


class BuildTrackDimmer(LightEntity, RestoreEntity):

    def __init__(self, hass, api, device):

        self._hass = hass
        self._api = api
        self._device = device

        self._entity_id = device.get("entityId")
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

    async def _async_set_power(
        self,
        state: str,
        brightness_percent: int,
    ):

        response = await self._api.call(
            endpoint=f"/controlDevice/{self._entity_id}",
            method="POST",
            payload={
                "entityId": self._entity_id,
                "entityKey": self._entity_key,
                "state": state,
                "speed": brightness_percent,
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
            self._attr_brightness = 255

        brightness_percent = int(
            (self._attr_brightness / 255) * 100
        )

        await self._async_set_power(
            "on",
            brightness_percent,
        )

    # -------------------------------------------------
    # TURN OFF
    # -------------------------------------------------

    async def async_turn_off(self, **kwargs):

        await self._async_set_power("off", 0)

    # -------------------------------------------------
    # REALTIME UPDATE
    # -------------------------------------------------

    async def async_update(self):
        """Realtime dimmer update from BuildTrack."""

        data = await self._api.call(
            endpoint="/readDeviceData",
            method="POST",
            payload={
                "entityId": self._entity_id,
                "entityKey": self._entity_key,
            },
        )

        _LOGGER.warning(
            "Realtime Dimmer Data | %s | %s",
            self._attr_name,
            data,
        )

        if not data:
            return

        state = str(data.get("state", "")).lower()

        self._attr_is_on = state == "on"

        speed = data.get("speed") or data.get("brightness")

        if speed is not None:
            try:
                self._attr_brightness = int(
                    (int(speed) / 100) * 255
                )
            except Exception:
                pass

        self.async_write_ha_state()