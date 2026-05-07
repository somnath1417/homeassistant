import asyncio
import logging

from datetime import timedelta

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACMode,
    HVACAction,
    ClimateEntityFeature,
)
from homeassistant.const import UnitOfTemperature

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=5)


async def async_setup_entry(hass, entry, async_add_entities, discovery_info=None):
    """Set up BuildTrack Climate platform."""
    data = hass.data[DOMAIN][entry.entry_id]
    devices = data["devices"]
    api = data["api"]

    climates = []

    for device in devices:
        if "THERMOSTAT" in device.get("type", []):
            climates.append(BuildTrackClimate(hass, api, device))

    async_add_entities(climates)


class BuildTrackClimate(ClimateEntity):
    """BuildTrack Thermostat Entity."""

    def __init__(self, hass, api, device):
        self._hass = hass
        self._api = api
        self._device = device

        self._entity_id = device.get("entityId")
        self._entity_key = device.get("entityKey")

        self._attr_name = device.get("entityName")
        self._attr_unique_id = self._entity_id

        self._temp_task = None

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_current_temperature = 24
        self._attr_target_temperature = 26
        self._attr_min_temp = 18
        self._attr_max_temp = 32
        self._attr_target_temperature_step = 1

        self._attr_hvac_modes = [
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.OFF,
        ]
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_action = HVACAction.OFF

        self._attr_fan_modes = ["low", "medium", "high"]
        self._attr_fan_mode = "low"

        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
        )

    async def async_set_temperature(self, **kwargs):
        """Handle temperature change from UI."""
        temperature = kwargs.get("temperature")

        if temperature is None:
            _LOGGER.warning(
                "Temperature not provided | Entity: %s",
                self.entity_id,
            )
            return

        self._attr_target_temperature = temperature
        self.async_write_ha_state()

        if self._temp_task:
            self._temp_task.cancel()

        self._temp_task = asyncio.create_task(
            self._delayed_temperature_call(temperature)
        )

    async def _delayed_temperature_call(self, temperature):
        """Delay API call to avoid rapid requests."""
        try:
            await asyncio.sleep(0.5)

            response = await self._api.call(
                endpoint=f"/setTemperature/{self._entity_id}",
                method="POST",
                payload={
                    "entityId": self._entity_id,
                    "entityKey": self._entity_key,
                    "temperature": temperature,
                },
            )

            _LOGGER.warning("Temperature RAW API RESPONSE: %s", response)

        except asyncio.CancelledError:
            pass

        except Exception as err:
            _LOGGER.exception(
                "ERROR: Exception while setting temperature | Entity: %s | Error: %s",
                self.entity_id,
                err,
            )

    async def async_set_hvac_mode(self, hvac_mode):
        """Set HVAC mode."""

        if hvac_mode not in self._attr_hvac_modes:
            return

        command_map = {
            HVACMode.COOL: "COOL",
            HVACMode.HEAT: "HEAT",
            HVACMode.OFF: "OFF",
        }

        command = command_map.get(hvac_mode)

        response = await self._api.call(
            endpoint=f"/controlDevice/{self._entity_id}",
            method="POST",
            payload={
                "entityId": self._entity_id,
                "entityKey": self._entity_key,
                "state": command,
            },
        )

        _LOGGER.warning("HVAC RAW RESPONSE: %s", response)

        if response:
            self._attr_hvac_mode = hvac_mode

            if hvac_mode == HVACMode.COOL:
                self._attr_hvac_action = HVACAction.COOLING
            elif hvac_mode == HVACMode.HEAT:
                self._attr_hvac_action = HVACAction.HEATING
            else:
                self._attr_hvac_action = HVACAction.OFF

            self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        """Set fan mode."""

        if fan_mode not in self._attr_fan_modes:
            return

        fan_command_map = {
            "low": "FAN_LOW",
            "medium": "FAN_MEDIUM",
            "high": "FAN_HIGH",
        }

        command = fan_command_map.get(fan_mode)

        response = await self._api.call(
            endpoint=f"/controlDevice/{self._entity_id}",
            method="POST",
            payload={
                "entityId": self._entity_id,
                "entityKey": self._entity_key,
                "state": command,
                "speed": self._attr_target_temperature,
            },
        )

        _LOGGER.warning("FAN RAW RESPONSE: %s", response)

        if response:
            self._attr_fan_mode = fan_mode
            self.async_write_ha_state()

    async def async_update(self):
        """Realtime thermostat update from BuildTrack."""

        data = await self._api.call(
            endpoint="/readDeviceData",
            method="POST",
            payload={
                "entityId": self._entity_id,
                "entityKey": self._entity_key,
            },
        )

        _LOGGER.warning(
            "Realtime Climate Data | %s | %s",
            self._attr_name,
            data,
        )

        if not data:
            return

        temperature = data.get("temperature")
        current_temperature = data.get("currentTemperature")
        state = str(data.get("state", "")).upper()
        fan_speed = str(data.get("fanSpeed", "")).lower()

        if temperature is not None:
            self._attr_target_temperature = float(temperature)

        if current_temperature is not None:
            self._attr_current_temperature = float(current_temperature)

        if state == "COOL":
            self._attr_hvac_mode = HVACMode.COOL
            self._attr_hvac_action = HVACAction.COOLING
        elif state == "HEAT":
            self._attr_hvac_mode = HVACMode.HEAT
            self._attr_hvac_action = HVACAction.HEATING
        elif state == "OFF":
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_hvac_action = HVACAction.OFF

        if fan_speed in self._attr_fan_modes:
            self._attr_fan_mode = fan_speed

        self.async_write_ha_state()