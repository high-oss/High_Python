# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""TOTP authentication.

The redirect consent flow (``/auth/generate-consent``, ``/auth/login``,
``/auth/consume-consent``) is deliberately not wrapped: it is built around a
browser page only a human can complete. Token introspection
(``/auth/validate-token``) is not wrapped either — a caller learns a token is
invalid from the next call's 401. See the README.
"""

from __future__ import annotations

from typing import Optional

import httpx

from .. import http_async, http_sync
from ..config import ResolvedConfig
from ..generated.models import AccessToken
from ._shared import parse


class AuthResource:
    def __init__(self, client: httpx.Client, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    def generate_access_token(self, client_id: str, t_otp: str, *, cancel_event=None) -> AccessToken:
        """Exchanges the API key plus a TOTP for a 24-hour access token."""
        data = http_sync.send_request(
            self._client, self._config, method="GET", path="/auth/generate-access-token", auth="apiKey",
            query={"clientId": client_id, "tOtp": t_otp}, cancel_event=cancel_event,
        )
        return parse(AccessToken, data)


class AsyncAuthResource:
    def __init__(self, client: httpx.AsyncClient, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    async def generate_access_token(self, client_id: str, t_otp: str) -> AccessToken:
        data = await http_async.send_request(
            self._client, self._config, method="GET", path="/auth/generate-access-token", auth="apiKey",
            query={"clientId": client_id, "tOtp": t_otp},
        )
        return parse(AccessToken, data)
