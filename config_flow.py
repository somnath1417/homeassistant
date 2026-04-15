import logging
from urllib.parse import urlencode

from aiohttp import web

from homeassistant import config_entries
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import AUTHORIZE_URL, DOMAIN, SCOPE, TOKEN_URL

_LOGGER = logging.getLogger(__name__)


class BuildTrackOAuthCallbackView(HomeAssistantView):
    requires_auth = False
    url = "/api/buildtrack/oauth/callback"
    name = "api:buildtrack:oauth:callback"

    async def get(self, request: web.Request) -> web.Response:
        """Handle OAuth callback from BuildTrack."""

        hass = request.app["hass"]

        code = request.query.get("code")
        state = request.query.get("state")
        error = request.query.get("error")

        _LOGGER.warning(
            "BuildTrack callback received: code=%s state=%s error=%s",
            code,
            state,
            error,
        )

        if not state:
            return web.Response(text="Missing state", status=400)

        await hass.config_entries.flow.async_configure(
            state,
            {
                "code": code,
                "state": state,
                "error": error,
            },
        )

        return web.Response(
            text="<script>window.close()</script>Authentication completed. You can close this window.",
            content_type="text/html",
        )


class BuildTrackConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Start BuildTrack OAuth flow."""

        _LOGGER.warning("===== BuildTrack Config Flow Started =====")

        domain_data = self.hass.data.get(DOMAIN, {})
        client_id = domain_data.get("client_id")
        client_secret = domain_data.get("client_secret")

        if not client_id or not client_secret:
            _LOGGER.error("BuildTrack client_id/client_secret not found in hass.data[DOMAIN]")
            return self.async_abort(reason="missing_credentials")

        if not self.hass.data.get(f"{DOMAIN}_callback_registered"):
            self.hass.http.register_view(BuildTrackOAuthCallbackView)
            self.hass.data[f"{DOMAIN}_callback_registered"] = True
            _LOGGER.warning("BuildTrack callback view registered")

        state = self.flow_id
        redirect_uri = "http://192.168.4.31:8123/api/buildtrack/oauth/callback"

        self.context["oauth_state"] = state
        self.context["redirect_uri"] = redirect_uri
        self.context["client_id"] = client_id

        params = {
            "scope": SCOPE,
            "state": state,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
        }

        auth_url = f"{AUTHORIZE_URL}?{urlencode(params)}"
        _LOGGER.warning("Generated BuildTrack authorize URL: %s", auth_url)

        return self.async_external_step(
            step_id="auth",
            url=auth_url,
        )

    async def async_step_auth(self, user_input=None):
        """Handle returned OAuth callback data."""

        _LOGGER.warning("Returned from external BuildTrack auth step")
        _LOGGER.warning("Auth callback user_input: %s", user_input)

        if not user_input:
            return self.async_abort(reason="missing_callback_data")

        returned_state = user_input.get("state")
        code = user_input.get("code")
        error = user_input.get("error")
        expected_state = self.context.get("oauth_state")

        if error:
            _LOGGER.error("OAuth error returned: %s", error)
            return self.async_abort(reason="oauth_error")

        if returned_state != expected_state:
            _LOGGER.error(
                "State mismatch. Expected=%s Returned=%s",
                expected_state,
                returned_state,
            )
            return self.async_abort(reason="state_mismatch")

        if not code:
            _LOGGER.error("Authorization code missing in callback")
            return self.async_abort(reason="missing_code")

        self.context["auth_code"] = code
        _LOGGER.warning("Authorization code received successfully")

        return self.async_external_step_done(next_step_id="auth_done")

    async def async_step_auth_done(self, user_input=None):
        """Exchange code for token and create entry."""

        _LOGGER.warning("Finishing BuildTrack auth flow")

        client_id = self.context.get("client_id")
        code = self.context.get("auth_code")
        redirect_uri = self.context.get("redirect_uri")

        if not client_id or not code or not redirect_uri:
            _LOGGER.error("Missing client_id/code/redirect_uri in flow context")
            return self.async_abort(reason="missing_callback_data")

        token_data = await self._exchange_code_for_token(code, redirect_uri)
        if not token_data:
            return self.async_abort(reason="token_exchange_failed")

        await self.async_set_unique_id("buildtrack_oauth")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="BuildTrack",
            data={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": SCOPE,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "token_type": token_data.get("token_type"),
                "expires_in": token_data.get("expires_in"),
            },
        )

    async def _exchange_code_for_token(self, code: str, redirect_uri: str):
        """Exchange authorization code for access token."""

        _LOGGER.warning("===== Starting token exchange =====")

        domain_data = self.hass.data.get(DOMAIN, {})
        client_id = domain_data.get("client_id")
        client_secret = domain_data.get("client_secret")

        if not client_id or not client_secret:
            _LOGGER.error("BuildTrack client_id/client_secret missing during token exchange")
            return None

        payload = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
        }

        session = async_get_clientsession(self.hass)

        try:
            async with session.post(
                TOKEN_URL,
                data=payload,
                headers=headers,
            ) as response:
                _LOGGER.warning("Token response status: %s", response.status)

                response_text = await response.text()
                _LOGGER.warning("Token raw response text: %s", response_text[:2000])

                if response.status != 200:
                    _LOGGER.error("Token endpoint returned non-200 response")
                    return None

                try:
                    data = await response.json(content_type=None)
                    _LOGGER.warning("Parsed token JSON: %s", data)

                    if not data.get("access_token"):
                        _LOGGER.error("access_token not found in token response")
                        return None

                    return data

                except Exception as json_error:
                    _LOGGER.exception(
                        "JSON parsing error during token exchange: %s",
                        json_error,
                    )
                    return None

        except Exception as token_error:
            _LOGGER.exception(
                "API call exception during token exchange: %s",
                token_error,
            )
            return None


"""
import logging
from urllib.parse import urlencode

from aiohttp import web

from homeassistant import config_entries
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import AUTHORIZE_URL, SCOPE, TOKEN_URL, DOMAIN

DOMAIN = "buildtrack"
_LOGGER = logging.getLogger(__name__)


class BuildTrackOAuthCallbackView(HomeAssistantView):
    requires_auth = False
    url = "/api/buildtrack/oauth/callback"
    name = "api:buildtrack:oauth:callback"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]

        code = request.query.get("code")
        state = request.query.get("state")
        error = request.query.get("error")

        if not state:
            return web.Response(text="Missing state", status=400)

        await hass.config_entries.flow.async_configure(
            state,
            {
                "code": code,
                "state": state,
                "error": error,
            },
        )

        return web.Response(
            text="<script>window.close()</script>Authentication completed. You can close this window.",
            content_type="text/html",
        )


class BuildTrackConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        _LOGGER.warning("===== BuildTrack Config Flow Started =====")

        CLIENT_ID  = self.hass.data.get("client_id")
        CLIENT_SECRET = self.hass.data.get("client_secret")

        if not self.hass.data.get(f"{DOMAIN}_callback_registered"):
            self.hass.http.register_view(BuildTrackOAuthCallbackView)
            self.hass.data[f"{DOMAIN}_callback_registered"] = True
            _LOGGER.warning("BuildTrack callback view registered")

        state = self.flow_id
        redirect_uri = "http://192.168.4.31:8123/api/buildtrack/oauth/callback"

        self.context["oauth_state"] = state
        self.context["redirect_uri"] = redirect_uri

        _LOGGER.warning("Using state: %s", state)
        _LOGGER.warning("Using redirect_uri: %s", redirect_uri)

        params = {
            "scope": SCOPE,
            "state": state,
            "client_id": CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
        }

        auth_url = f"{AUTHORIZE_URL}?{urlencode(params)}"
        _LOGGER.warning("Generated BuildTrack authorize URL: %s", auth_url)

        return self.async_external_step(
            step_id="auth",
            url=auth_url,
        )

    async def async_step_auth(self, user_input=None):
        _LOGGER.warning("Returned from external BuildTrack auth step")
        _LOGGER.warning("Auth callback user_input: %s", user_input)

        if not user_input:
            return self.async_abort(reason="missing_callback_data")

        returned_state = user_input.get("state")
        code = user_input.get("code")
        error = user_input.get("error")
        expected_state = self.context.get("oauth_state")

        if error:
            _LOGGER.error("OAuth error returned: %s", error)
            return self.async_abort(reason="oauth_error")

        if returned_state != expected_state:
            _LOGGER.error(
                "State mismatch. Expected=%s Returned=%s",
                expected_state,
                returned_state,
            )
            return self.async_abort(reason="state_mismatch")

        if not code:
            _LOGGER.error("Authorization code missing in callback")
            return self.async_abort(reason="missing_code")

        _LOGGER.warning("Authorization code received successfully")
        self.context["auth_code"] = code

        return self.async_external_step_done(next_step_id="auth_done")

    async def async_step_auth_done(self, user_input=None):
        _LOGGER.warning("Finishing BuildTrack auth flow")

        CLIENT_ID  = self.hass.data.get("client_id")

        code = self.context.get("auth_code")
        redirect_uri = self.context.get("redirect_uri")

        if not code or not redirect_uri:
            return self.async_abort(reason="missing_callback_data")

        token_data = await self._exchange_code_for_token(code, redirect_uri)
        if not token_data:
            return self.async_abort(reason="token_exchange_failed")

        await self.async_set_unique_id("buildtrack_oauth")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="BuildTrack",
            data={
                "client_id": CLIENT_ID,
                "redirect_uri": redirect_uri,
                "scope": SCOPE,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "token_type": token_data.get("token_type"),
                "expires_in": token_data.get("expires_in"),
            },
        )

    async def _exchange_code_for_token(self, code: str, redirect_uri: str):
        _LOGGER.warning("===== Starting token exchange =====")

        CLIENT_ID  = self.hass.data.get("client_id")
        CLIENT_SECRET = self.hass.data.get("client_secret")

        payload = {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36"
            ),
        }

        session = async_get_clientsession(self.hass)

        try:
            async with session.post(
                TOKEN_URL,
                data=payload,
                headers=headers,
            ) as response:
                _LOGGER.warning("Token response status: %s", response.status)

                response_text = await response.text()
                _LOGGER.warning("Token raw response text: %s", response_text[:2000])

                if response.status != 200:
                    _LOGGER.error("Token endpoint returned non-200 response")
                    return None

                try:
                    data = await response.json(content_type=None)
                    _LOGGER.warning("Parsed token JSON: %s", data)

                    if not data.get("access_token"):
                        _LOGGER.error("access_token not found in token response")
                        return None

                    return data

                except Exception as json_error:
                    _LOGGER.exception(
                        "JSON parsing error during token exchange: %s",
                        json_error,
                    )
                    return None

        except Exception as token_error:
            _LOGGER.exception(
                "API call exception during token exchange: %s",
                token_error,
            )
            return None

"""
