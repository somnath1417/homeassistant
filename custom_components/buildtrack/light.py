import logging

from datetime import timedelta, datetime

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

    _LOGGER.info("BuildTrack Devices : %s", devices)

    for device in devices:

        if "LIGHT DIMMER" in device.get("type", []):
            lights.append(BuildTrackDimmer(hass, api, device))

        elif "LIGHT" in device.get("type", []):
            lights.append(BuildTrackLight(hass, api, device))

    async_add_entities(lights)


# =====================================================
# NORMAL LIGHT
# =====================================================

class BuildTrackLight(LightEntity):

    def __init__(self, hass, api, device):

        self._hass = hass
        self._api = api
        self._device = device

        self._entity_id = device.get("entityId")
        self._entity_key = device.get("entityKey")

        self._attr_name = device.get("entityName")
        self._attr_unique_id = self._entity_id

        self._attr_supported_color_modes = {
            ColorMode.ONOFF
        }

        self._attr_color_mode = ColorMode.ONOFF

        self._attr_is_on = False

        self._last_local_change = None

    # -------------------------------------------------
    # TURN ON
    # -------------------------------------------------

    async def async_turn_on(self, **kwargs):

        self._instant_set_power(
            "on",
            True,
        )

    # -------------------------------------------------
    # TURN OFF
    # -------------------------------------------------

    async def async_turn_off(self, **kwargs):

        self._instant_set_power(
            "off",
            False,
        )

    # -------------------------------------------------
    # INSTANT LOCAL UPDATE
    # -------------------------------------------------

    def _instant_set_power(
        self,
        state: str,
        is_on: bool,
    ):

        old_state = self._attr_is_on

        self._attr_is_on = is_on

        self._last_local_change = datetime.now()

        self.async_write_ha_state()

        self._hass.async_create_task(
            self._send_power_to_api(
                state,
                old_state,
            )
        )

    # -------------------------------------------------
    # BACKGROUND API
    # -------------------------------------------------

    async def _send_power_to_api(
        self,
        state: str,
        old_state: bool,
    ):

        response = await self._api.call(
            endpoint=f"/controlDevice/{self._entity_id}",
            method="POST",
            payload={
                "entityId": self._entity_id,
                "entityKey": self._entity_key,
                "state": state,
            },
        )

        if response is None:

            self._attr_is_on = old_state

            self.async_write_ha_state()

    # -------------------------------------------------
    # REALTIME UPDATE
    # -------------------------------------------------

    async def async_update(self):

        if self._last_local_change:

            diff = (
                datetime.now() - self._last_local_change
            ).total_seconds()

            if diff < 3:
                return

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

        state = str(
            data.get("state", "")
        ).lower()

        if state in ["on", "1", "true"]:

            self._attr_is_on = True

        elif state in ["off", "0", "false"]:

            self._attr_is_on = False

        self.async_write_ha_state()


class BuildTrackDimmer(
    LightEntity,
    RestoreEntity,
):

    should_poll = True

    def __init__(
        self,
        hass,
        api,
        device,
    ):

        self._hass = hass
        self._api = api
        self._device = device

        self._entity_id = device.get("entityId")
        self._entity_key = device.get("entityKey")

        self._attr_name = device.get("entityName")

        self._attr_unique_id = self._entity_id

        self._attr_supported_color_modes = {
            ColorMode.BRIGHTNESS
        }

        self._attr_color_mode = (
            ColorMode.BRIGHTNESS
        )

        self._is_on = False

        # NEVER None
        self._brightness = 255

        self._last_local_change = None

    # -------------------------------------------------
    # REQUIRED PROPERTIES
    # -------------------------------------------------

    @property
    def is_on(self):

        return self._is_on

    @property
    def brightness(self):

        return self._brightness

    @property
    def available(self):

        return True

    # -------------------------------------------------
    # RESTORE STATE
    # -------------------------------------------------

    async def async_added_to_hass(self):

        last_state = await self.async_get_last_state()

        if last_state:

            self._is_on = (
                last_state.state == "on"
            )

            brightness = (
                last_state.attributes.get(
                    "brightness"
                )
            )

            # PROTECTION
            if brightness is not None:
                self._brightness = brightness

    # -------------------------------------------------
    # TURN ON
    # -------------------------------------------------

    async def async_turn_on(
        self,
        **kwargs,
    ):

        brightness = kwargs.get(
            "brightness"
        )

        if brightness is not None:
            self._brightness = brightness

        # PROTECTION
        if (
            self._brightness is None
            or self._brightness <= 0
        ):
            self._brightness = 255

        brightness_percent = int(
            (self._brightness / 255) * 100
        )

        self._is_on = True

        self.async_write_ha_state()

        self._last_local_change = (
            datetime.now()
        )

        self._hass.async_create_task(
            self._api.call(
                endpoint=f"/controlDevice/{self._entity_id}",
                method="POST",
                payload={
                    "entityId": self._entity_id,
                    "entityKey": self._entity_key,
                    "state": "on",
                    "speed": brightness_percent,
                },
            )
        )

    # -------------------------------------------------
    # TURN OFF
    # -------------------------------------------------

    async def async_turn_off(
        self,
        **kwargs,
    ):

        self._is_on = False
        self._brightness = 0

        self.async_write_ha_state()

        self._last_local_change = (
            datetime.now()
        )

        self._hass.async_create_task(
            self._api.call(
                endpoint=f"/controlDevice/{self._entity_id}",
                method="POST",
                payload={
                    "entityId": self._entity_id,
                    "entityKey": self._entity_key,
                    "state": "off",
                    "speed": 0,
                },
            )
        )

    # -------------------------------------------------
    # REALTIME UPDATE
    # -------------------------------------------------

    async def async_update(self):

        if self._last_local_change:

            diff = (
                datetime.now()
                - self._last_local_change
            ).total_seconds()

            if diff < 3:
                return

        data = await self._api.call(
            endpoint="/readDeviceData",
            method="POST",
            payload={
                "entityId": self._entity_id,
                "entityKey": self._entity_key,
            },
        )

        _LOGGER.warning(
            "DIMMER REALTIME DATA = %s",
            data,
        )

        if not data:
            return

        state = str(
            data.get("state", "")
        ).lower()

        speed = data.get("speed")

        # -------------------------------------------------
        # BRIGHTNESS
        # -------------------------------------------------

        if speed is not None:

            try:

                speed_int = int(speed)

                speed_int = max(
                    0,
                    min(speed_int, 100),
                )

                self._brightness = int(
                    (speed_int / 100) * 255
                )

                self._is_on = (
                    speed_int > 0
                )

            except Exception as err:

                _LOGGER.warning(
                    "DIMMER SPEED ERROR = %s",
                    err,
                )

        # -------------------------------------------------
        # EXPLICIT STATE
        # -------------------------------------------------

        if state in [
            "on",
            "1",
            "true",
        ]:

            self._is_on = True

        elif state in [
            "off",
            "0",
            "false",
        ]:

            self._is_on = False

            # PROTECTION
            if (
                self._brightness is not None
                and self._brightness > 0
            ):
                self._brightness = 0

        _LOGGER.warning(
            "FINAL DIMMER | is_on=%s | brightness=%s",
            self._is_on,
            self._brightness,
        )

        self.async_write_ha_state()