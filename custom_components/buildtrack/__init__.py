import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    CONF_API_URL,
    CONF_AUTH_URL,
    CONF_AUTH_TYPE,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
)
from .api import BuildTrackAPI

PLATFORMS = ["button", "light", "scene", "climate"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.warning("BuildTrack async_setup loaded")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.warning("===== BuildTrack async_setup_entry started =====")

    hass.data.setdefault(DOMAIN, {})

    api_url = entry.data.get(CONF_API_URL)
    auth_url = entry.data.get(CONF_AUTH_URL)
    auth_type = entry.data.get(CONF_AUTH_TYPE)

    username = entry.data.get("username")
    password = entry.data.get("password")

    client_id = entry.data.get(CONF_CLIENT_ID)
    client_secret = entry.data.get(CONF_CLIENT_SECRET)

    redirect_uri = entry.data.get("redirect_uri")

    access_token = entry.data.get("access_token")
    refresh_token = entry.data.get("refresh_token")
    token_type = entry.data.get("token_type")
    expires_in = entry.data.get("expires_in")
    scope = entry.data.get("scope")

    if not api_url:
        _LOGGER.error("BuildTrack api_url missing in config entry")
        return False

    if not auth_url:
        _LOGGER.error("BuildTrack auth_url missing in config entry")
        return False

    if not client_id or not client_secret:
        _LOGGER.error("BuildTrack client_id/client_secret missing in config entry")
        return False

    if not access_token:
        _LOGGER.error("BuildTrack access_token missing in config entry")
        return False

    api = BuildTrackAPI(
        hass=hass,
        api_url=api_url,
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        refresh_token=refresh_token,
    )

    try:
        devices = await api.call(
            endpoint="/getDevices",
            method="GET",
            response_key="devices",
        )
    except Exception as err:
        _LOGGER.exception("Failed to fetch BuildTrack devices during setup: %s", err)
        return False

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "devices": devices or [],
        "api_url": api_url,
        "auth_url": auth_url,
        "auth_type": auth_type,
        "username": username,
        "password": password,
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": token_type,
        "expires_in": expires_in,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "entry": entry,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.warning(
        "BuildTrack entry setup completed: %s, devices=%s",
        entry.entry_id,
        len(devices or []),
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    _LOGGER.warning("BuildTrack entry unloaded: %s", entry.entry_id)

    return unload_ok
