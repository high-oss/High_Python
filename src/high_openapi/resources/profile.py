# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

from __future__ import annotations

import httpx

from .. import http_async, http_sync
from ..config import ResolvedConfig
from ..generated.models import Profile
from ._shared import parse

__all__ = ["ProfileResource", "AsyncProfileResource"]


class ProfileResource:
    def __init__(self, client: httpx.Client, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    def get(self, *, cancel_event=None) -> Profile:
        """The account holder's identity, demat and bank details. PAN, Aadhaar
        and bank account numbers are masked to their last four characters."""
        data = http_sync.send_request(
            self._client, self._config, method="GET", path="/profile", auth="bearer",
            cancel_event=cancel_event,
        )
        return parse(Profile, data)


class AsyncProfileResource:
    def __init__(self, client: httpx.AsyncClient, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    async def get(self) -> Profile:
        data = await http_async.send_request(
            self._client, self._config, method="GET", path="/profile", auth="bearer",
        )
        return parse(Profile, data)
