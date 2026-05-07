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

        # instant UI update
        self._attr_is_on = is_on

        self._last_local_change = datetime.now()

        self.async_write_ha_state()

        # background API call
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

        # rollback if failed
        if response is None:

            self._attr_is_on = old_state

            self.async_write_ha_state()

    # -------------------------------------------------
    # REALTIME UPDATE
    # -------------------------------------------------

    async def async_update(self):

        # skip polling after local update
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


# =====================================================
# DIMMER LIGHT
# =====================================================

class BuildTrackDimmer(
    LightEntity,
    RestoreEntity,
):

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

        self._attr_is_on = False

        self._attr_brightness = 128

        self._last_local_change = None

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

            self._attr_is_on = (
                last_state.state == "on"
            )

            if (
                "brightness"
                in last_state.attributes
            ):

                self._attr_brightness = (
                    last_state.attributes[
                        "brightness"
                    ]
                )

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

            self._attr_brightness = brightness

        if (
            self._attr_brightness is None
            or self._attr_brightness <= 0
        ):

            self._attr_brightness = 255

        brightness_percent = int(
            (
                self._attr_brightness
                / 255
            ) * 100
        )

        self._instant_set_power(
            "on",
            brightness_percent,
        )

    # -------------------------------------------------
    # TURN OFF
    # -------------------------------------------------

    async def async_turn_off(
        self,
        **kwargs,
    ):

        self._instant_set_power(
            "off",
            0,
        )

    # -------------------------------------------------
    # INSTANT LOCAL UPDATE
    # -------------------------------------------------

    def _instant_set_power(
        self,
        state: str,
        brightness_percent: int,
    ):

        old_state = self._attr_is_on

        old_brightness = (
            self._attr_brightness
        )

        self._attr_is_on = (
            state.lower() == "on"
        )

        if state.lower() == "off":

            self._attr_brightness = 0

        else:

            self._attr_brightness = int(
                (
                    brightness_percent
                    / 100
                ) * 255
            )

        self._last_local_change = (
            datetime.now()
        )

        self.async_write_ha_state()

        self._hass.async_create_task(
            self._send_power_to_api(
                state,
                brightness_percent,
                old_state,
                old_brightness,
            )
        )

    # -------------------------------------------------
    # BACKGROUND API
    # -------------------------------------------------

    async def _send_power_to_api(
        self,
        state: str,
        brightness_percent: int,
        old_state: bool,
        old_brightness: int,
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

        # rollback if failed
        if response is None:

            self._attr_is_on = old_state

            self._attr_brightness = (
                old_brightness
            )

            self.async_write_ha_state()

    # -------------------------------------------------
    # REALTIME UPDATE
    # -------------------------------------------------

    async def async_update(self):
        """Realtime dimmer update."""

        # skip polling after local update
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
            "Realtime Dimmer Data | %s | %s",
            self._attr_name,
            data,
        )

        if not data:
            return

        # -------------------------------------------------
        # GET BRIGHTNESS VALUE
        # -------------------------------------------------

        speed = (
            data.get("speed")
            or data.get("brightness")
            or data.get("level")
            or data.get("value")
        )

        # -------------------------------------------------
        # UPDATE BRIGHTNESS + STATE
        # -------------------------------------------------

        if speed is not None:

            try:

                speed_int = int(
                    float(speed)
                )

                # clamp
                speed_int = max(
                    0,
                    min(speed_int, 100),
                )

                # update brightness
                self._attr_brightness = int(
                    (
                        speed_int
                        / 100
                    ) * 255
                )

                # auto ON/OFF
                self._attr_is_on = (
                    speed_int > 0
                )

                _LOGGER.warning(
                    "Dimmer realtime brightness update | %s | speed=%s | brightness=%s",
                    self._attr_name,
                    speed_int,
                    self._attr_brightness,
                )

            except Exception as err:

                _LOGGER.warning(
                    "Dimmer speed parse error | %s | %s",
                    self._attr_name,
                    err,
                )

        # -------------------------------------------------
        # HANDLE EXPLICIT STATE
        # -------------------------------------------------

        state = str(
            data.get("state", "")
        ).lower()

        if state in [
            "on",
            "1",
            "true",
        ]:

            self._attr_is_on = True

        elif state in [
            "off",
            "0",
            "false",
        ]:

            # only OFF if brightness 0
            if self._attr_brightness <= 0:

                self._attr_is_on = False

        self.async_write_ha_state()