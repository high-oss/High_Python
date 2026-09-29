# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Renders the canonical index-feed table into a committed Python module.

The canonical source is ``High/sdk/index-feed-map.json`` — one level above
every SDK repo, shared by all five. It is joined once, by hand, from the live
scrip master's index rows and the vendor's index lists (see the datafeed
plan, Phase 1), and is not re-derived at runtime: each SDK renders it into
its own language and commits the result, so subscribing to an index needs no
network call and no JSON parse at import time.

The source is an object with two lists:

- ``indices`` — scripKeys that resolve to exactly one index. Rendered as
  ``INDEX_FEED_MAP``.
- ``ambiguous`` — scripKeys the scrip master shares between two *different*
  indices (a real data defect, confirmed against the live scrip master, not
  a rendering artefact). Rendered as ``AMBIGUOUS_INDEX_KEYS``. These are
  deliberately excluded from ``INDEX_FEED_MAP``: resolving one to either
  candidate would silently stream the wrong index under the caller's own
  name, with plausible-looking prices, so nobody would ever notice.
  ``translate.py`` rejects them by name instead, listing both candidates.

Run this from a full ``High/sdk`` checkout (the JSON lives outside this repo,
so it is not available inside the Docker container the test suite normally
runs in unless the fixture copy below is kept in sync):

    python scripts/regenerate_index_map.py

It rewrites ``src/high_openapi/feed/_index_map.py`` in place, and also
refreshes the committed test fixture (``tests/fixtures/index-feed-map.json``)
with the exact source bytes, so ``tests/test_feed_index_map.py`` can rebuild
and diff against a copy that always ships with the repo instead of skipping
when only this repo is mounted. Review the diff and commit all three
together.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "src" / "high_openapi" / "feed" / "_index_map.py"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "index-feed-map.json"

# High/sdk/index-feed-map.json, one directory above every SDK repo.
DEFAULT_SOURCE = REPO_ROOT.parent / "index-feed-map.json"


def render(source: dict) -> str:
    indices = source["indices"]
    ambiguous = source["ambiguous"]

    # The source is expected to already guarantee this (that is the whole
    # point of splitting ambiguous out) — checked here so a future upstream
    # regression is a loud regeneration failure, not a silently wrong table.
    seen = set()
    for entry in indices:
        key = entry["scripKey"]
        if key in seen:
            raise SystemExit(
                f"{key!r} appears more than once in indices — it belongs in ambiguous instead. "
                f"Fix the source before regenerating."
            )
        seen.add(key)
    ambiguous_keys = {entry["scripKey"] for entry in ambiguous}
    overlap = seen & ambiguous_keys
    if overlap:
        raise SystemExit(f"scripKey(s) in both indices and ambiguous: {sorted(overlap)}")

    lines = [
        "# Copyright (c) 2026 Truestock",
        "# SPDX-License-Identifier: MIT",
        "",
        "# GENERATED FILE — do not edit by hand.",
        "#",
        "# Rendered from High/sdk/index-feed-map.json by",
        "# scripts/regenerate_index_map.py. That file is the canonical, hand-joined",
        "# table of every HIGH index scrip key the feed carries — see the datafeed",
        "# plan, Phase 1. Regenerate and commit both together (and the refreshed",
        "# tests/fixtures/index-feed-map.json copy); do not hand-edit this module.",
        "# tests/test_feed_index_map.py rebuilds this table from that fixture and",
        "# asserts this module still matches it.",
        "#",
        f"# {len(indices)} unambiguous entries (INDEX_FEED_MAP).",
        f"# {len(ambiguous)} scripKeys the scrip master shares between two different",
        "# indices — a confirmed data defect, not a rendering artefact. Deliberately",
        "# excluded from INDEX_FEED_MAP and listed in AMBIGUOUS_INDEX_KEYS instead, so",
        "# subscribing to one raises naming both candidates rather than silently",
        "# resolving to whichever one happened to win a tie-break.",
        "",
        "from __future__ import annotations",
        "",
        "from typing import Dict, Tuple",
        "",
        "# scripKey -> (feedSegment, feedSymbol)",
        "INDEX_FEED_MAP: Dict[str, Tuple[str, str]] = {",
    ]
    for entry in indices:
        lines.append(f"    {entry['scripKey']!r}: ({entry['feedSegment']!r}, {entry['feedSymbol']!r}),")
    lines.append("}")
    lines.append("")
    lines.append("# scripKey -> the two (or more) index names the scrip master maps it to.")
    lines.append("AMBIGUOUS_INDEX_KEYS: Dict[str, Tuple[str, ...]] = {")
    for entry in ambiguous:
        candidates = ", ".join(repr(c) for c in entry["candidates"])
        lines.append(f"    {entry['scripKey']!r}: ({candidates}{',' if len(entry['candidates']) == 1 else ''}),")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    source_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source_path.exists():
        raise SystemExit(
            f"Canonical source not found at {source_path}. Run this from a full High/sdk "
            f"checkout, or pass its path explicitly: "
            f"python scripts/regenerate_index_map.py <path to index-feed-map.json>"
        )
    raw_text = source_path.read_text(encoding="utf-8")
    source = json.loads(raw_text)

    OUTPUT_PATH.write_text(render(source), encoding="utf-8", newline="\n")
    print(f"Wrote {len(source['indices'])} indices + {len(source['ambiguous'])} ambiguous to {OUTPUT_PATH}")

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(raw_text, encoding="utf-8", newline="\n")
    print(f"Refreshed fixture at {FIXTURE_PATH}")


if __name__ == "__main__":
    main()
