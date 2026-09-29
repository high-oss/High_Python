# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

# GENERATED FILE — do not edit by hand.
#
# Rendered from High/sdk/index-feed-map.json by
# scripts/regenerate_index_map.py. That file is the canonical, hand-joined
# table of every HIGH index scrip key the feed carries — see the datafeed
# plan, Phase 1. Regenerate and commit both together (and the refreshed
# tests/fixtures/index-feed-map.json copy); do not hand-edit this module.
# tests/test_feed_index_map.py rebuilds this table from that fixture and
# asserts this module still matches it.
#
# 81 unambiguous entries (INDEX_FEED_MAP).
# 6 scripKeys the scrip master shares between two different
# indices — a confirmed data defect, not a rendering artefact. Deliberately
# excluded from INDEX_FEED_MAP and listed in AMBIGUOUS_INDEX_KEYS instead, so
# subscribing to one raises naming both candidates rather than silently
# resolving to whichever one happened to win a tie-break.

from __future__ import annotations

from typing import Dict, Tuple

# scripKey -> (feedSegment, feedSymbol)
INDEX_FEED_MAP: Dict[str, Tuple[str, str]] = {
    'BSE@19000': ('bse_cm', 'SENSEX'),
    'BSE@19001': ('bse_cm', 'BSEPSU'),
    'BSE@19002': ('bse_cm', 'BSE100'),
    'BSE@19003': ('bse_cm', 'BSE200'),
    'BSE@19004': ('bse_cm', 'BSE500'),
    'BSE@19005': ('bse_cm', 'BSE IT'),
    'BSE@19006': ('bse_cm', 'BSEFMC'),
    'BSE@19007': ('bse_cm', 'BSE CG'),
    'BSE@19008': ('bse_cm', 'BSE CD'),
    'BSE@19009': ('bse_cm', 'BSE HC'),
    'BSE@19011': ('bse_cm', 'TECK'),
    'BSE@19012': ('bse_cm', 'BANKEX'),
    'BSE@19013': ('bse_cm', 'AUTO'),
    'BSE@19014': ('bse_cm', 'METAL'),
    'BSE@19015': ('bse_cm', 'CPSE'),
    'BSE@19016': ('bse_cm', 'MIDCAP'),
    'BSE@19017': ('bse_cm', 'SMLCAP'),
    'BSE@19019': ('bse_cm', 'DOL100'),
    'BSE@19020': ('bse_cm', 'DOL200'),
    'BSE@19051': ('bse_cm', 'OILGAS'),
    'BSE@19052': ('bse_cm', 'POWER'),
    'BSE@19053': ('bse_cm', 'REALTY'),
    'BSE@19054': ('bse_cm', 'BSEIPO'),
    'BSE@19059': ('bse_cm', 'SMEIPO'),
    'BSE@19060': ('bse_cm', 'INFRA'),
    'BSE@19089': ('bse_cm', 'LMI250'),
    'BSE@39': ('bse_cm', 'ENERGY'),
    'BSE@40': ('bse_cm', 'FINSER'),
    'BSE@41': ('bse_cm', 'INDSTR'),
    'BSE@42': ('bse_cm', 'LRGCAP'),
    'BSE@43': ('bse_cm', 'MIDSEL'),
    'BSE@44': ('bse_cm', 'SMLSEL'),
    'BSE@45': ('bse_cm', 'TELCOM'),
    'BSE@47': ('bse_cm', 'SNSX50'),
    'BSE@48': ('bse_cm', 'SNXT50'),
    'BSE@55': ('bse_cm', 'MID150'),
    'BSE@58': ('bse_cm', 'MSL400'),
    'NSE@25998': ('nse_cm', 'Nifty 500'),
    'NSE@26000': ('nse_cm', 'Nifty 50'),
    'NSE@26001': ('nse_cm', 'Nifty GrowSect 15'),
    'NSE@26008': ('nse_cm', 'Nifty IT'),
    'NSE@26009': ('nse_cm', 'Nifty Bank'),
    'NSE@26012': ('nse_cm', 'Nifty 100'),
    'NSE@26013': ('nse_cm', 'Nifty Next 50'),
    'NSE@26014': ('nse_cm', 'Nifty Midcap 50'),
    'NSE@26017': ('nse_cm', 'India VIX'),
    'NSE@26018': ('nse_cm', 'Nifty Pharma'),
    'NSE@26019': ('nse_cm', 'Nifty Infra'),
    'NSE@26021': ('nse_cm', 'Nifty Realty'),
    'NSE@26022': ('nse_cm', 'Nifty MNC'),
    'NSE@26024': ('nse_cm', 'Nifty PSE'),
    'NSE@26026': ('nse_cm', 'Nifty Serv Sector'),
    'NSE@26033': ('nse_cm', 'Nifty Auto'),
    'NSE@26035': ('nse_cm', 'Nifty Consumption'),
    'NSE@26036': ('nse_cm', 'Nifty 200'),
    'NSE@26037': ('nse_cm', 'Nifty Fin Service'),
    'NSE@26038': ('nse_cm', 'Nifty50 Div Point'),
    'NSE@26041': ('nse_cm', 'Nifty CPSE'),
    'NSE@26042': ('nse_cm', 'Nifty50 PR 1x Inv'),
    'NSE@26043': ('nse_cm', 'Nifty50 TR 2x Lev'),
    'NSE@26048': ('nse_cm', 'NIFTY100 Qualty30'),
    'NSE@26049': ('nse_cm', 'Nifty GS 8 13Yr'),
    'NSE@26050': ('nse_cm', 'Nifty GS 10Yr'),
    'NSE@26051': ('nse_cm', 'Nifty GS 10Yr Cln'),
    'NSE@26052': ('nse_cm', 'Nifty GS 4 8Yr'),
    'NSE@26053': ('nse_cm', 'Nifty GS 11 15Yr'),
    'NSE@26054': ('nse_cm', 'Nifty GS 15YrPlus'),
    'NSE@26055': ('nse_cm', 'Nifty GS Compsite'),
    'NSE@26056': ('nse_cm', 'NIFTY50 EQL Wgt'),
    'NSE@26057': ('nse_cm', 'NIFTY100 EQL Wgt'),
    'NSE@26058': ('nse_cm', 'NIFTY100 LowVol30'),
    'NSE@26059': ('nse_cm', 'NIFTY Alpha 50'),
    'NSE@26070': ('nse_cm', 'Nifty50 Value 20'),
    'NSE@26074': ('nse_cm', 'NIFTY MID SELECT'),
    'NSE@26076': ('nse_cm', 'Nifty Pvt Bank'),
    'NSE@26085': ('nse_cm', 'Nifty Media'),
    'NSE@26090': ('nse_cm', 'NIFTY MIDCAP 150'),
    'NSE@26091': ('nse_cm', 'NIFTY SMLCAP 50'),
    'NSE@26092': ('nse_cm', 'NIFTY SMLCAP 250'),
    'NSE@26093': ('nse_cm', 'NIFTY MIDSML 400'),
    'NSE@26094': ('nse_cm', 'NIFTY200 QUALTY30'),
}

# scripKey -> the two (or more) index names the scrip master maps it to.
AMBIGUOUS_INDEX_KEYS: Dict[str, Tuple[str, ...]] = {
    'NSE@26002': ('Nifty FMCG', 'Nifty50 PR 2x Lev'),
    'NSE@26020': ('Nifty Energy', 'Nifty PSU Bank'),
    'NSE@26034': ('Nifty Div Opps 50', 'Nifty Metal'),
    'NSE@26040': ('Nifty Commodities', 'Nifty100 Liq 15'),
    'NSE@26044': ('NIFTY MIDCAP 100', 'Nifty50 TR 1x Inv'),
    'NSE@26046': ('NIFTY SMLCAP 100', 'Nifty Mid Liq 15'),
}
