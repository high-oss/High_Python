# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Runnable quickstart for the live datafeed (production only — there is no
sandbox feed).

    HIGH_ACCESS_TOKEN=... python examples/feed_quickstart.py

Async form — the primary way to consume the feed, one event at a time:

    async for event in feed:
        ...

A synchronous callback form is also available via ``HighFeed`` (see the
README's Live datafeed section) for callers who are not already in an
asyncio application.
"""

from __future__ import annotations

import asyncio

from high_openapi import AsyncHighFeed, Depth, IndexTick, Quote


async def main() -> None:
    feed = AsyncHighFeed()  # picks up HIGH_ACCESS_TOKEN; environment defaults to production
    await feed.connect()

    await feed.subscribe_quotes(["NSE@2885"])       # Reliance Industries, by HIGH scrip key
    await feed.subscribe_depth(["NSE@2885"])         # five-level market depth for the same scrip
    await feed.subscribe_indices(["NSE@26000"])      # Nifty 50 — from the committed index table

    count = 0
    async for event in feed:
        if isinstance(event, Quote):
            print(f"quote  {event.scrip_key}: LTP={event.last_traded_price} changed={sorted(event.changed_fields)}")
        elif isinstance(event, Depth):
            best_bid = event.bids[0] if event.bids else None
            print(f"depth  {event.scrip_key}: levels={event.level_count} best_bid={best_bid}")
        elif isinstance(event, IndexTick):
            print(f"index  {event.scrip_key}: value={event.index_value}")

        count += 1
        if count >= 20:
            break

    await feed.close()


if __name__ == "__main__":
    asyncio.run(main())
