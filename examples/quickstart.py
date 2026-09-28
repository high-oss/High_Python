# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Runnable quickstart for the sync client.

    HIGH_ENVIRONMENT=sandbox HIGH_API_KEY=... HIGH_ACCESS_TOKEN=... python examples/quickstart.py

Credentials are read from the environment (HIGH_API_KEY / HIGH_ACCESS_TOKEN /
HIGH_ENVIRONMENT), so nothing is hard-coded here. See the README's
Configuration section for the full option list.
"""

from __future__ import annotations

from high_openapi import HighApiError, HighClient


def main() -> None:
    with HighClient() as high:  # picks up HIGH_* environment variables
        try:
            funds = high.portfolio.funds()
        except HighApiError as error:
            print(f"HIGH API error: status={error.status} code={error.code} request_id={error.request_id}")
            raise

        print(f"Available balance: {funds.availableBalance}")

        quotes = high.scrips.quotes({"symbols": ["RELIANCE-EQ"]})
        reliance = quotes.get("RELIANCE-EQ")
        if reliance is not None:
            print(f"RELIANCE-EQ LTP: {reliance.LTP}")

        status = high.market.status()
        print(f"Market status: {status.exchangeStatus}")


if __name__ == "__main__":
    main()
