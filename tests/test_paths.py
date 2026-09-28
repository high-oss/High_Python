# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

import pytest

from high_openapi.paths import path_of


def test_interpolates_a_plain_parameter():
    assert path_of("/orders/{orderId}", {"orderId": "2609250000123456"}) == "/orders/2609250000123456"


def test_encodes_characters_that_would_otherwise_change_the_path():
    assert path_of("/scrips/{symbol}/depth", {"symbol": "M&M-EQ"}) == "/scrips/M%26M-EQ/depth"
    assert path_of("/scrips/{symbol}/depth", {"symbol": "NIFTY 50"}) == "/scrips/NIFTY%2050/depth"


def test_encodes_a_slash_so_a_parameter_can_never_add_a_path_segment():
    assert path_of("/scrips/{symbol}/depth", {"symbol": "a/../b"}) == "/scrips/a%2F..%2Fb/depth"


def test_interpolates_several_parameters():
    assert (
        path_of("/scrips/{symbol}/{type}/expiries", {"symbol": "NIFTY", "type": "OPT"})
        == "/scrips/NIFTY/OPT/expiries"
    )


def test_accepts_a_numeric_parameter():
    assert path_of("/orders/{orderId}", {"orderId": 42}) == "/orders/42"


def test_refuses_a_template_whose_parameter_was_not_supplied():
    with pytest.raises(ValueError, match="orderId"):
        path_of("/orders/{orderId}", {})
