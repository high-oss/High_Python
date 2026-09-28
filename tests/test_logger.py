# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

import re

import pytest

from high_openapi.logger import LOG_LEVELS, create_logger, redact_body, redact_url


class Sink:
    def __init__(self):
        self.lines = []

    def _push(self, level, message, detail=None):
        self.lines.append({"level": level, "message": message, "detail": detail})

    def error(self, message, detail=None):
        self._push("error", message, detail)

    def warn(self, message, detail=None):
        self._push("warn", message, detail)

    def info(self, message, detail=None):
        self._push("info", message, detail)

    def debug(self, message, detail=None):
        self._push("debug", message, detail)


def test_log_levels_ordered_least_to_most_verbose():
    assert LOG_LEVELS == ("silent", "error", "warn", "info", "debug")


def test_prints_nothing_at_silent():
    sink = Sink()
    log = create_logger("silent", sink)
    log.error("boom")
    log.warn("hmm")
    log.info("fyi")
    log.debug("detail")
    assert sink.lines == []


def test_prints_chosen_level_and_more_severe():
    sink = Sink()
    log = create_logger("warn", sink)
    log.error("boom")
    log.warn("hmm")
    log.info("fyi")
    log.debug("detail")
    assert [line["level"] for line in sink.lines] == ["error", "warn"]


def test_prints_everything_at_debug():
    sink = Sink()
    log = create_logger("debug", sink)
    log.error("a")
    log.warn("b")
    log.info("c")
    log.debug("d")
    assert [line["level"] for line in sink.lines] == ["error", "warn", "info", "debug"]


def test_never_evaluates_a_suppressed_level():
    sink = Sink()
    log = create_logger("error", sink)
    assert log.enabled("debug") is False
    assert log.enabled("error") is True


def test_defaults_to_console_when_no_sink_supplied(capsys):
    log = create_logger("error")
    log.error("boom")
    captured = capsys.readouterr()
    assert "boom" in captured.err


def test_redacts_totp_and_credentials_from_url():
    url = "https://openapi.high.live/v1/auth/generate-access-token?clientId=C1&tOtp=123456"
    safe = redact_url(url)
    assert "123456" not in safe
    assert "tOtp=REDACTED" in safe
    assert "clientId=C1" in safe


def test_redacts_every_sensitive_query_param_it_knows():
    url = "https://h.example/v1/x?apiKey=k&accessToken=t&tokenId=ti&stepToken=st&consentId=c"
    safe = redact_url(url)
    for secret in ["=k", "=t&", "=ti", "=st"]:
        assert secret not in safe
    assert "consentId=c" in safe


def test_leaves_a_url_without_secrets_untouched():
    url = "https://openapi.high.live/v1/orders/list"
    assert redact_url(url) == url


def test_returns_malformed_url_unchanged_rather_than_throwing():
    assert redact_url("not a url") == "not a url"


def test_every_line_has_iso8601_timestamp_and_level():
    sink = Sink()
    create_logger("debug", sink).warn("something happened")
    assert re.match(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z WARN {2}something happened$",
        sink.lines[0]["message"],
    )


def test_pads_the_level_so_lines_align():
    sink = Sink()
    log = create_logger("debug", sink)
    log.error("a")
    log.debug("b")
    levels = [line["message"].split("Z ")[1].split(" ")[0] for line in sink.lines]
    assert levels == ["ERROR", "DEBUG"]
    columns = {line["message"].index(line["message"].rstrip()[-1]) for line in sink.lines}
    assert len(columns) == 1


def test_redact_body_masks_credential_shaped_keys_at_any_depth():
    safe = redact_body(
        {
            "tradingSymbol": "RELIANCE-EQ",
            "nested": {
                "accessToken": "SECRET",
                "tOtp": "123456",
                "apiKey": "K",
                "password": "p",
                "pin": "1234",
            },
        }
    )
    assert safe["tradingSymbol"] == "RELIANCE-EQ"
    for key in ["accessToken", "tOtp", "apiKey", "password", "pin"]:
        assert safe["nested"][key] == "REDACTED"


def test_redact_body_walks_lists():
    safe = redact_body([{"tOtp": "1"}, {"quantity": 10}])
    assert safe[0]["tOtp"] == "REDACTED"
    assert safe[1]["quantity"] == 10


def test_redact_body_truncates_oversized_payload():
    big = {"symbols": [f"SYM{i}-EQ" for i in range(500)]}
    import json

    safe = json.dumps(redact_body(big))
    assert len(safe) < 2000
    assert "truncated" in safe


def test_redact_body_passes_primitives_and_none_through():
    assert redact_body(None) is None
    assert redact_body(42) == 42
