# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Frame builders and message classification — pure, no socket involved."""

from high_openapi.feed._protocol import (
    auth_ack_error,
    auth_frame,
    chunk,
    classify_message,
    snapshot_frame,
    subscribe_frame,
    unsubscribe_frame,
)
from high_openapi.feed.errors import HighFeedInvalidTokenError, HighFeedNoDataPlanError


class TestFrameBuilders:
    def test_auth_frame_carries_no_mode(self):
        frame = auth_frame("secret-token")
        assert frame == {"type": "cn", "sessionid": "secret-token"}
        assert "mode" not in frame

    def test_subscribe_frame_joins_scrips_with_ampersand(self):
        frame = subscribe_frame("quote", ["nse_cm|11536", "nse_cm|22", "bse_cm|532540"], 1)
        assert frame == {"type": "mws", "scrips": "nse_cm|11536&nse_cm|22&bse_cm|532540", "channelnum": 1}

    def test_depth_and_index_use_their_own_prefixes(self):
        assert subscribe_frame("depth", ["nse_cm|22"], 2)["type"] == "dps"
        assert subscribe_frame("index", ["nse_cm|Nifty 50"], 3)["type"] == "ifs"

    def test_unsubscribe_and_snapshot_suffixes(self):
        assert unsubscribe_frame("quote", ["nse_cm|22"], 1)["type"] == "mwu"
        assert unsubscribe_frame("depth", ["nse_cm|22"], 1)["type"] == "dpu"
        assert unsubscribe_frame("index", ["nse_cm|Nifty 50"], 1)["type"] == "ifu"
        assert snapshot_frame("quote", ["nse_cm|22"], 1)["type"] == "mwsp"


class TestChunk:
    def test_splits_into_groups_of_at_most_size(self):
        groups = list(chunk(["a", "b", "c", "d", "e"], 2))
        assert groups == [["a", "b"], ["c", "d"], ["e"]]

    def test_exact_multiple(self):
        assert list(chunk(["a", "b", "c", "d"], 2)) == [["a", "b"], ["c", "d"]]

    def test_size_larger_than_input_yields_one_group(self):
        assert list(chunk(["a"], 10)) == [["a"]]

    def test_empty_input_yields_nothing(self):
        assert list(chunk([], 5)) == []


class TestClassifyMessage:
    def test_auth_ack_ok(self):
        raw = {
            "stat": "Ok", "type": "cn", "msg": "successful", "stCode": 200,
            "maxScripPerConn": 500, "maxScripPerReq": 200, "sType": "v2.0",
        }
        classified = classify_message(raw)
        assert classified["kind"] == "auth_ack"
        assert classified["ok"] is True
        assert classified["max_scrip_per_conn"] == 500
        assert classified["max_scrip_per_req"] == 200
        assert auth_ack_error(classified) is None

    def test_auth_ack_not_ok(self):
        raw = {"stat": "NotOk", "type": "cn", "msg": "failed", "stCode": 11001}
        classified = classify_message(raw)
        assert classified["kind"] == "auth_ack"
        assert classified["ok"] is False
        error = auth_ack_error(classified)
        assert error is not None
        assert error.st_code == 11001

    def test_sub_ack(self):
        raw = [{"stat": "Ok", "type": "sub", "msg": "successful", "stCode": 200}]
        classified = classify_message(raw)
        assert classified["kind"] == "sub_ack"
        assert classified["items"] == raw

    def test_unsub_ack(self):
        raw = [{"stat": "Ok", "type": "unsub", "msg": "successful", "stCode": 200}]
        assert classify_message(raw)["kind"] == "sub_ack"

    def test_tick_array_is_not_mistaken_for_an_ack(self):
        raw = [{"t": "sf", "e": "nse_cm", "tk": "2885", "ltp": "100.50"}]
        classified = classify_message(raw)
        assert classified["kind"] == "ticks"
        assert classified["items"] == raw

    def test_unrecognised_shape_is_unknown_not_a_crash(self):
        assert classify_message("just a string")["kind"] == "unknown"
        assert classify_message(42)["kind"] == "unknown"
        assert classify_message(None)["kind"] == "unknown"


class TestAuthAckErrorClassification:
    """See feed/errors.py's module docstring: the exact stCode for a missing
    data plan vs. an invalid token is not pinned by the plan, so this is a
    best-effort match on the ack's own msg text."""

    def test_a_missing_data_plan_message_is_named(self):
        error = auth_ack_error(classify_message({"stat": "NotOk", "type": "cn", "msg": "no data plan subscribed", "stCode": 11050}))
        assert isinstance(error, HighFeedNoDataPlanError)

    def test_an_invalid_token_message_is_named(self):
        error = auth_ack_error(classify_message({"stat": "NotOk", "type": "cn", "msg": "invalid session token", "stCode": 11051}))
        assert isinstance(error, HighFeedInvalidTokenError)

    def test_the_documented_invalid_field_count_code_is_not_misclassified_as_a_bad_token(self):
        error = auth_ack_error(classify_message({"stat": "NotOk", "type": "cn", "msg": "invalid field count", "stCode": 11002}))
        assert not isinstance(error, HighFeedInvalidTokenError)
        assert not isinstance(error, HighFeedNoDataPlanError)
        assert error.st_code == 11002

    def test_an_unrecognised_message_keeps_its_code_and_text_intact(self):
        error = auth_ack_error(classify_message({"stat": "NotOk", "type": "cn", "msg": "something else entirely", "stCode": 11099}))
        assert not isinstance(error, HighFeedInvalidTokenError)
        assert not isinstance(error, HighFeedNoDataPlanError)
        assert error.st_code == 11099
        assert error.msg == "something else entirely"
