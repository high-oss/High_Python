# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Interpolates a path template, percent-encoding every value.

Trading symbols legitimately contain ``&`` and spaces (``M&M-EQ``,
``NIFTY 50``), which change the request if interpolated raw. Encoding is not
optional — including encoding a stray ``/``, so a parameter can never add a
path segment of its own.
"""

from __future__ import annotations

import re
from typing import Dict, Union
from urllib.parse import quote

_PARAM = re.compile(r"\{(\w+)\}")


def path_of(template: str, params: Dict[str, Union[str, int]]) -> str:
    def replace(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name not in params:
            raise ValueError(f'Missing path parameter "{name}" for {template}')
        return quote(str(params[name]), safe="")

    return _PARAM.sub(replace, template)
