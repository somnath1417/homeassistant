import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .api import BuildTrackAPI

PLATFORMS = ["light", "scene", "climate"]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up BuildTrack integration.

    YAML credentials are not used now.
    Credentials come from config_flow form.
    """
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.warning("BuildTrack async_setup loaded")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BuildTrack from config entry."""

    _LOGGER.warning("===== BuildTrack async_setup_entry started =====")

    hass.data.setdefault(DOMAIN, {})

    username = entry.data.get("username")
    password = entry.data.get("password")
    client_id = entry.data.get("client_id")
    client_secret = entry.data.get("client_secret")
    redirect_uri = entry.data.get("redirect_uri")

    access_token = entry.data.get("access_token")
    refresh_token = entry.data.get("refresh_token")
    token_type = entry.data.get("token_type")
    expires_in = entry.data.get("expires_in")
    scope = entry.data.get("scope")

    if not client_id or not client_secret:
        _LOGGER.error("BuildTrack client_id/client_secret missing in config entry")
        return False

    if not access_token:
        _LOGGER.error("BuildTrack access_token missing in config entry")
        return False

    _LOGGER.warning("BuildTrack credentials loaded from config entry")
    _LOGGER.warning("BuildTrack redirect_uri: %s", redirect_uri)
    _LOGGER.warning("BuildTrack access_token available: %s", bool(access_token))

    api = BuildTrackAPI(
        hass=hass,
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
    """Unload BuildTrack config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    _LOGGER.warning("BuildTrack entry unloaded: %s", entry.entry_id)

    return unload_ok
