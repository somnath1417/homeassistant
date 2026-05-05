import logging
from urllib.parse import urlencode

import voluptuous as vol
from aiohttp import web

from homeassistant import config_entries
from homeassistant.components.http import HomeAssistantView
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url, NoURLAvailableError

from .const import AUTHORIZE_URL, DOMAIN, SCOPE, TOKEN_URL

_LOGGER = logging.getLogger(__name__)

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_REDIRECT_URI = "redirect_uri"


class BuildTrackOAuthCallbackView(HomeAssistantView):
    requires_auth = False
    url = "/api/buildtrack/oauth/callback"
    name = "api:buildtrack:oauth:callback"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]

        code = request.query.get("code")
        state = request.query.get("state")
        error = request.query.get("error")

        _LOGGER.warning(
            "BuildTrack callback received: code=%s state=%s error=%s",
            bool(code),
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
        errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_USERNAME): str,
                        vol.Required(CONF_PASSWORD): str,
                        vol.Required(CONF_CLIENT_ID): str,
                        vol.Required(CONF_CLIENT_SECRET): str,
                    }
                ),
                errors=errors,
            )

        if not self.hass.data.get(f"{DOMAIN}_callback_registered"):
            self.hass.http.register_view(BuildTrackOAuthCallbackView)
            self.hass.data[f"{DOMAIN}_callback_registered"] = True

        try:
            base_url = get_url(self.hass, prefer_external=False)
        except NoURLAvailableError:
            errors["base"] = "ha_url_not_found"
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_USERNAME, default=user_input.get(CONF_USERNAME, "")): str,
                        vol.Required(CONF_PASSWORD): str,
                        vol.Required(CONF_CLIENT_ID, default=user_input.get(CONF_CLIENT_ID, "")): str,
                        vol.Required(CONF_CLIENT_SECRET): str,
                    }
                ),
                errors=errors,
            )

        redirect_uri = f"{base_url.rstrip('/')}/api/buildtrack/oauth/callback"

        state = self.flow_id

        self.context["oauth_state"] = state
        self.context[CONF_USERNAME] = user_input[CONF_USERNAME]
        self.context[CONF_PASSWORD] = user_input[CONF_PASSWORD]
        self.context[CONF_CLIENT_ID] = user_input[CONF_CLIENT_ID]
        self.context[CONF_CLIENT_SECRET] = user_input[CONF_CLIENT_SECRET]
        self.context[CONF_REDIRECT_URI] = redirect_uri

        params = {
            "scope": SCOPE,
            "state": state,
            "client_id": user_input[CONF_CLIENT_ID],
            "redirect_uri": redirect_uri,
            "response_type": "code",
        }

        auth_url = f"{AUTHORIZE_URL}?{urlencode(params)}"

        _LOGGER.warning("BuildTrack redirect_uri: %s", redirect_uri)
        _LOGGER.warning("Generated BuildTrack authorize URL: %s", auth_url)

        return self.async_external_step(
            step_id="auth",
            url=auth_url,
        )

    async def async_step_auth(self, user_input=None):
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
            return self.async_abort(reason="missing_code")

        self.context["auth_code"] = code

        return self.async_external_step_done(next_step_id="auth_done")

    async def async_step_auth_done(self, user_input=None):
        username = self.context.get(CONF_USERNAME)
        password = self.context.get(CONF_PASSWORD)
        client_id = self.context.get(CONF_CLIENT_ID)
        client_secret = self.context.get(CONF_CLIENT_SECRET)
        redirect_uri = self.context.get(CONF_REDIRECT_URI)
        code = self.context.get("auth_code")

        if not all([username, password, client_id, client_secret, redirect_uri, code]):
            return self.async_abort(reason="missing_callback_data")

        token_data = await self._exchange_code_for_token(
            username=username,
            password=password,
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            redirect_uri=redirect_uri,
        )

        if not token_data:
            return self.async_abort(reason="token_exchange_failed")

        await self.async_set_unique_id("buildtrack_oauth")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="BuildTrack",
            data={
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
                CONF_CLIENT_ID: client_id,
                CONF_CLIENT_SECRET: client_secret,
                CONF_REDIRECT_URI: redirect_uri,
                "scope": SCOPE,
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "token_type": token_data.get("token_type"),
                "expires_in": token_data.get("expires_in"),
            },
        )

    async def _exchange_code_for_token(
        self,
        username: str,
        password: str,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
    ):
        payload = {
            "grant_type": "authorization_code",
            "username": username,
            "password": password,
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json,text/plain,*/*",
        }

        session = async_get_clientsession(self.hass)

        try:
            async with session.post(
                TOKEN_URL,
                data=payload,
                headers=headers,
            ) as response:
                response_text = await response.text()
                _LOGGER.warning("Token response status: %s", response.status)
                _LOGGER.warning("Token raw response: %s", response_text[:1000])

                if response.status != 200:
                    return None

                data = await response.json(content_type=None)

                if not data.get("access_token"):
                    return None

                return data

        except Exception as err:
            _LOGGER.exception("Token exchange failed: %s", err)
            return None
