# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Rebuilds the committed index table from the canonical source and asserts
it still matches — the same guarantee ``test_review_findings.py`` gives the
generated OpenAPI types, applied to ``scripts/regenerate_index_map.py``'s
output (datafeed plan, Phase 1: "each SDK ships a test that rebuilds the
join from the committed source").

The canonical source, ``High/sdk/index-feed-map.json``, lives one directory
above every SDK repo — it is shared by all five and is not part of this
repo, so it is not present inside the Docker container the project's own
test command mounts. Rather than skip there, this rebuilds from a pinned
copy committed at ``tests/fixtures/index-feed-map.json`` instead, so the
check runs in CI every time. ``scripts/regenerate_index_map.py`` refreshes
that fixture together with the generated module whenever it is run for
real against the canonical file — the two are meant to move together,
exactly like the REST client's ``spec.lock.json`` and its generated types.
"""

import json
from pathlib import Path

from high_openapi.feed._index_map import AMBIGUOUS_INDEX_KEYS, INDEX_FEED_MAP

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SOURCE = REPO_ROOT / "tests" / "fixtures" / "index-feed-map.json"


class TestCommittedTableSanity:
    def test_has_eighty_one_unambiguous_entries(self):
        assert len(INDEX_FEED_MAP) == 81

    def test_every_entry_is_a_segment_symbol_pair(self):
        for scrip_key, (segment, symbol) in INDEX_FEED_MAP.items():
            assert isinstance(scrip_key, str) and "@" in scrip_key
            assert segment in ("nse_cm", "bse_cm")
            assert isinstance(symbol, str) and symbol != ""

    def test_the_four_upstream_rows_with_no_feed_counterpart_are_absent(self):
        # See the datafeed plan, Phase 1: HANGSENG BEES-NAV, S&P BSE
        # CARBONEX, S&P BSE GREENEX and S&P BSE DOLLEX 30 have no feed
        # counterpart and must never appear here.
        absent_keys = {"NSE@26016", "BSE@19058", "BSE@19081", "BSE@19018"}
        assert absent_keys.isdisjoint(INDEX_FEED_MAP.keys())
        assert absent_keys.isdisjoint(AMBIGUOUS_INDEX_KEYS.keys())

    def test_known_examples_from_the_plan(self):
        assert INDEX_FEED_MAP["NSE@26000"] == ("nse_cm", "Nifty 50")
        assert INDEX_FEED_MAP["NSE@26009"] == ("nse_cm", "Nifty Bank")
        assert INDEX_FEED_MAP["BSE@19000"] == ("bse_cm", "SENSEX")


class TestAmbiguousIndexKeys:
    """Six scripKeys the live scrip master maps to two different indices —
    a confirmed data defect (per the coordinator, checked against the live
    scrip master), not a rendering artefact. Deliberately excluded from
    INDEX_FEED_MAP: no resolution here would be safe, since any pick is
    silent and looks entirely plausible downstream."""

    def test_has_six_ambiguous_keys(self):
        assert len(AMBIGUOUS_INDEX_KEYS) == 6

    def test_none_of_them_are_also_in_the_unambiguous_table(self):
        assert set(AMBIGUOUS_INDEX_KEYS).isdisjoint(INDEX_FEED_MAP.keys())

    def test_each_carries_its_two_candidate_names(self):
        assert AMBIGUOUS_INDEX_KEYS["NSE@26002"] == ("Nifty FMCG", "Nifty50 PR 2x Lev")
        assert AMBIGUOUS_INDEX_KEYS["NSE@26020"] == ("Nifty Energy", "Nifty PSU Bank")
        assert AMBIGUOUS_INDEX_KEYS["NSE@26034"] == ("Nifty Div Opps 50", "Nifty Metal")
        assert AMBIGUOUS_INDEX_KEYS["NSE@26040"] == ("Nifty Commodities", "Nifty100 Liq 15")
        assert AMBIGUOUS_INDEX_KEYS["NSE@26044"] == ("NIFTY MIDCAP 100", "Nifty50 TR 1x Inv")
        assert AMBIGUOUS_INDEX_KEYS["NSE@26046"] == ("NIFTY SMLCAP 100", "Nifty Mid Liq 15")


class TestRebuildMatchesTheCommittedModule:
    def test_rebuilding_from_the_fixture_matches_the_committed_table(self):
        source = json.loads(FIXTURE_SOURCE.read_text(encoding="utf-8"))

        rebuilt_indices = {
            entry["scripKey"]: (entry["feedSegment"], entry["feedSymbol"]) for entry in source["indices"]
        }
        assert rebuilt_indices == INDEX_FEED_MAP

        rebuilt_ambiguous = {entry["scripKey"]: tuple(entry["candidates"]) for entry in source["ambiguous"]}
        assert rebuilt_ambiguous == AMBIGUOUS_INDEX_KEYS

    def test_the_fixture_and_the_committed_module_agree_on_totals(self):
        # A cheap early signal if someone updates one without the other —
        # the precise-match test above would also catch it, but this fails
        # with a much shorter message.
        source = json.loads(FIXTURE_SOURCE.read_text(encoding="utf-8"))
        assert len(source["indices"]) == len(INDEX_FEED_MAP)
        assert len(source["ambiguous"]) == len(AMBIGUOUS_INDEX_KEYS)
