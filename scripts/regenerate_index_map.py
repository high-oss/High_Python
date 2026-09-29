# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Renders the canonical index-feed table into a committed Python module.

The canonical source is ``High/sdk/index-feed-map.json`` — one level above
every SDK repo, shared by all five. It is joined once, by hand, from the live
scrip master's index rows and the vendor's index lists (see the datafeed plan,
Phase 1), and is not re-derived at runtime: each SDK renders it into its own
language and commits the result, so subscribing to an index needs no network
call and no JSON parse at import time.

Run this from a full ``High/sdk`` checkout (the JSON lives outside this repo,
so it is not available inside the Docker container the test suite normally
runs in — see ``tests/test_index_map.py``, which skips its rebuild-and-diff
check when the source file is not reachable):

    python scripts/regenerate_index_map.py

It rewrites ``src/high_openapi/feed/_index_map.py`` in place. Review the diff
and commit both files together with the source commit noted in the header.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "src" / "high_openapi" / "feed" / "_index_map.py"

# High/sdk/index-feed-map.json, one directory above every SDK repo.
DEFAULT_SOURCE = REPO_ROOT.parent / "index-feed-map.json"


def render(entries: list) -> str:
    # The source has been observed to list a handful of scripKeys twice,
    # with genuinely different feedSegment/feedSymbol values (e.g.
    # NSE@26002 as both "Nifty FMCG" and "Nifty50 PR 2x Lev") — not a
    # rendering bug, a real ambiguity in the canonical file itself. Building
    # a dict keyed by scripKey resolves it the same way every language's
    # hashmap literal would: the row that appears LAST in the source array
    # wins. That is deterministic and identical across all five SDKs (they
    # all iterate the same JSON array in the same order), so it is a safe
    # default resolution — but it is silent unless flagged here, so a
    # maintainer regenerating this file sees exactly which keys collided
    # and which symbol won.
    seen = {}
    duplicates = []
    for entry in entries:
        key = entry["scripKey"]
        if key in seen:
            duplicates.append((key, seen[key], entry))
        seen[key] = entry

    lines = [
        "# Copyright (c) 2026 Truestock",
        "# SPDX-License-Identifier: MIT",
        "",
        "# GENERATED FILE — do not edit by hand.",
        "#",
        "# Rendered from High/sdk/index-feed-map.json by",
        "# scripts/regenerate_index_map.py. That file is the canonical, hand-joined",
        "# table of every HIGH index scrip key the feed carries — see the datafeed",
        "# plan, Phase 1. Regenerate and commit both together; do not hand-edit this",
        "# module. tests/test_feed_index_map.py rebuilds this table from the source",
        "# JSON (when it is reachable) and asserts this module still matches it.",
        "#",
        f"# {len(entries)} rows in the source; {len(seen)} unique scripKeys below.",
    ]
    if duplicates:
        lines.append("#")
        lines.append(
            f"# {len(duplicates)} scripKey(s) appear more than once in the source, with different "
            f"feedSymbol values. The LAST occurrence in the source array wins (see this script's"
        )
        lines.append("# render() docstring comment) — listed here so the resolution is not silent:")
        for key, first, last in duplicates:
            lines.append(f"#   {key}: {first['feedSymbol']!r} (dropped) -> {last['feedSymbol']!r} (kept)")
    lines += [
        "",
        "from __future__ import annotations",
        "",
        "from typing import Dict, Tuple",
        "",
        "# scripKey -> (feedSegment, feedSymbol)",
        "INDEX_FEED_MAP: Dict[str, Tuple[str, str]] = {",
    ]
    for entry in entries:
        scrip_key = entry["scripKey"]
        feed_segment = entry["feedSegment"]
        feed_symbol = entry["feedSymbol"]
        lines.append(f"    {scrip_key!r}: ({feed_segment!r}, {feed_symbol!r}),")
    lines.append("}")
    lines.append("")

    if duplicates:
        print(f"WARNING: {len(duplicates)} duplicate scripKey(s) in the source — see the generated header.")
        for key, first, last in duplicates:
            print(f"  {key}: {first['feedSymbol']!r} (dropped) -> {last['feedSymbol']!r} (kept)")

    return "\n".join(lines)


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.exists():
        raise SystemExit(
            f"Canonical source not found at {source}. Run this from a full High/sdk "
            f"checkout, or pass its path explicitly: "
            f"python scripts/regenerate_index_map.py <path to index-feed-map.json>"
        )
    entries = json.loads(source.read_text(encoding="utf-8"))
    OUTPUT_PATH.write_text(render(entries), encoding="utf-8", newline="\n")
    print(f"Wrote {len(entries)} entries to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
