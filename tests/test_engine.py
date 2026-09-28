# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

from datetime import datetime, timezone

from high_openapi._engine import encode_query, is_retryable_method, retry_after_ms


def test_reads_a_delay_in_seconds():
    assert retry_after_ms("2") == 2000
    assert retry_after_ms("0") == 0


def test_reads_an_http_date_and_converts_it_to_a_delay():
    now = datetime(2026, 9, 28, 10, 0, 0, tzinfo=timezone.utc).timestamp() * 1000
    assert retry_after_ms("Mon, 28 Sep 2026 10:00:05 GMT", now) == 5000


def test_never_returns_a_negative_delay_for_a_date_in_the_past():
    now = datetime(2026, 9, 28, 10, 0, 10, tzinfo=timezone.utc).timestamp() * 1000
    assert retry_after_ms("Mon, 28 Sep 2026 10:00:05 GMT", now) == 0


def test_ignores_a_missing_or_unparseable_header():
    assert retry_after_ms(None) is None
    assert retry_after_ms("soon") is None
    assert retry_after_ms("") is None


def test_is_retryable_method_is_case_insensitive():
    assert is_retryable_method("get") is True
    assert is_retryable_method("GET") is True
    assert is_retryable_method("head") is True
    assert is_retryable_method("post") is False
    assert is_retryable_method("PATCH") is False
    assert is_retryable_method("delete") is False


def test_encode_query_skips_none_values():
    qs = encode_query({"clientId": "C1", "tOtp": 123456, "unused": None})
    assert "clientId=C1" in qs
    assert "tOtp=123456" in qs
    assert "unused" not in qs


def test_encode_query_lowercases_booleans():
    assert encode_query({"flag": True}) == "flag=true"
    assert encode_query({"flag": False}) == "flag=false"


def test_encode_query_empty():
    assert encode_query(None) == ""
    assert encode_query({}) == ""
