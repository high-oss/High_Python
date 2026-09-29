# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Rebuilds the committed index table from the canonical source and asserts
it still matches — the same guarantee ``test_review_findings.py`` gives the
generated OpenAPI types, applied to ``scripts/regenerate_index_map.py``'s
output (datafeed plan, Phase 1: "each SDK ships a test that rebuilds the
join from the committed source").

The canonical source, ``High/sdk/index-feed-map.json``, lives one directory
above every SDK repo — it is shared by all five and is not part of this
repo. It is therefore not present inside the Docker container the project's
own test command mounts (only ``high-sdk-python`` itself), so the
rebuild-and-diff check skips there rather than failing on an environment
difference; it runs for real from a full ``High/sdk`` checkout, exactly
where ``scripts/regenerate_index_map.py`` itself expects to be run from.
"""

import json
from pathlib import Path

import pytest

from high_openapi.feed._index_map import INDEX_FEED_MAP

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_SOURCE = REPO_ROOT.parent / "index-feed-map.json"


# The canonical source lists 93 rows, but 6 scripKeys appear twice with a
# genuinely different feedSymbol — not a rendering bug, a real ambiguity in
# the source file (see scripts/regenerate_index_map.py's render() docstring
# comment). A dict keyed by scripKey resolves that the same way every
# language's hashmap literal would: the row appearing LAST in the source
# array wins, deterministically and identically across all five SDKs.
_KNOWN_SOURCE_DUPLICATES = {
    "NSE@26002": "Nifty50 PR 2x Lev",
    "NSE@26020": "Nifty PSU Bank",
    "NSE@26034": "Nifty Metal",
    "NSE@26040": "Nifty100 Liq 15",
    "NSE@26044": "Nifty50 TR 1x Inv",
    "NSE@26046": "NIFTY SMLCAP 100",
}


class TestCommittedTableSanity:
    def test_has_eighty_seven_unique_scrip_keys_after_resolving_source_duplicates(self):
        assert len(INDEX_FEED_MAP) == 93 - len(_KNOWN_SOURCE_DUPLICATES)

    def test_the_known_source_duplicates_resolve_to_the_last_occurrence(self):
        for scrip_key, expected_symbol in _KNOWN_SOURCE_DUPLICATES.items():
            assert INDEX_FEED_MAP[scrip_key][1] == expected_symbol

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

    def test_known_examples_from_the_plan(self):
        assert INDEX_FEED_MAP["NSE@26000"] == ("nse_cm", "Nifty 50")
        assert INDEX_FEED_MAP["NSE@26009"] == ("nse_cm", "Nifty Bank")
        assert INDEX_FEED_MAP["BSE@19000"] == ("bse_cm", "SENSEX")


class TestRebuildMatchesTheCommittedModule:
    def test_rebuilding_from_the_canonical_source_matches_the_committed_table(self):
        if not CANONICAL_SOURCE.exists():
            pytest.skip(
                f"canonical source not reachable at {CANONICAL_SOURCE} in this environment "
                f"(expected outside the project's own Docker test container — see module docstring)"
            )
        entries = json.loads(CANONICAL_SOURCE.read_text(encoding="utf-8"))
        rebuilt = {entry["scripKey"]: (entry["feedSegment"], entry["feedSymbol"]) for entry in entries}
        assert rebuilt == INDEX_FEED_MAP
