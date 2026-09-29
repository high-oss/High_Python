# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

import json
from pathlib import Path

from high_openapi.generated import models

SPEC_PATH = Path(__file__).resolve().parent.parent / "src" / "high_openapi" / "generated" / "openapi.json"


def test_covers_every_operation_in_the_pinned_spec():
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    operations = [
        method
        for item in spec["paths"].values()
        for method in item
        if method in ("get", "post", "put", "delete", "patch")
    ]
    # 27 wrapped-or-excluded operations from the original contract, plus the
    # instrument list manifest (GET /instruments) added alongside it.
    assert len(operations) == 28


def test_exposes_the_shared_component_schemas_the_facades_return():
    # Field-presence checks, not full instantiation — Order and Funds carry
    # many required nested fields; this is the runtime analogue of the Node
    # suite's compile-time `Pick<Order, 'orderId'>` assertion.
    assert "orderId" in models.Order.model_fields
    assert "availableBalance" in models.Funds.model_fields


def test_exposes_the_instruments_manifest_and_file_models():
    # Generated, not hand-written — the SDK's instruments resource parses
    # into these directly rather than re-declaring the manifest shape.
    assert "columns" in models.InstrumentsManifest.model_fields
    assert "files" in models.InstrumentsManifest.model_fields
    assert "url" in models.InstrumentFile.model_fields
    assert set(models.Instrument) == {
        models.Instrument.all, models.Instrument.equity, models.Instrument.derivatives,
        models.Instrument.commodity, models.Instrument.etfs,
    }


def test_exposes_the_request_models_the_facades_wrap():
    place = models.PlaceOrderRequest(
        tradeSide="B",
        productType="DELIVERY",
        flavor="REGULAR",
        orderType="LIMIT",
        validity="DAY",
        quantity=10,
        isAMO=False,
    )
    assert place.tradeSide.value == "B"
