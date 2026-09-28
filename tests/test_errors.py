# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

from high_openapi.errors import ERROR_CODES, HighApiError, error_from_response


def test_high_api_error_is_an_exception_with_useful_attributes():
    error = HighApiError("Order rejected", status=400, code="ORDER_REJECTED")
    assert isinstance(error, Exception)
    assert error.__class__.__name__ == "HighApiError"
    assert str(error) == "Order rejected"
    assert error.status == 400
    assert error.code == "ORDER_REJECTED"


def test_error_from_response_maps_the_documented_envelope():
    error = error_from_response(
        400, {"requestId": "a1b2c3", "code": "ORDER_REJECTED", "message": "Insufficient funds"}
    )
    assert error.status == 400
    assert error.code == "ORDER_REJECTED"
    assert error.request_id == "a1b2c3"
    assert str(error) == "Insufficient funds"
    assert error.messages == ["Insufficient funds"]


def test_error_from_response_keeps_every_message_when_the_api_returns_a_list():
    error = error_from_response(
        400,
        {
            "requestId": "a1b2c3",
            "code": "VALIDATION_ERROR",
            "message": ["quantity must be positive", "price is required"],
        },
    )
    assert error.messages == ["quantity must be positive", "price is required"]
    assert str(error) == "quantity must be positive; price is required"


def test_error_from_response_survives_a_non_json_body_and_still_reports_status():
    error = error_from_response(502, None, "<html><body>502 Bad Gateway</body></html>")
    assert error.status == 502
    assert error.code is None
    assert "502" in str(error)
    assert isinstance(error, HighApiError)


def test_error_from_response_falls_back_to_the_status_when_body_carries_no_message():
    error = error_from_response(500, {"requestId": "a1b2c3"})
    assert "500" in str(error)
    assert error.request_id == "a1b2c3"


def test_error_from_response_accepts_a_code_outside_the_documented_catalogue():
    error = error_from_response(403, {"code": "DATA_PLAN_REQUIRED", "message": "Upgrade needed"})
    assert error.code == "DATA_PLAN_REQUIRED"


def test_error_codes_carries_the_documented_catalogue():
    assert "ORDER_REJECTED" in ERROR_CODES
    assert "VALIDATION_ERROR" in ERROR_CODES
    assert len(ERROR_CODES) > 20
