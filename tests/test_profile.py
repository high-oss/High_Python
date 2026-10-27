# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

from high_openapi.client import AsyncHighClient, HighClient

from .server import send_json, start_server

PROFILE = {
    "clientId": "HS1234", "name": "Asha Verma", "email": "asha.verma@example.com", "mobile": "9876543210",
    "pan": "XXXXXX234F", "aadhaar": "XXXXXXXX9012", "depository": "CDSL", "boCode": "1208160000123456",
    "dpCode": "12081600", "isPOAApproved": True, "isNRI": False, "isMTFEnabled": True,
    "segmentsAllowed": ["NSE_CASH", "NSE_FNO"],
    "address": {"address": "12, MG Road", "city": "Bengaluru", "state": "Karnataka", "pinCode": "560001"},
    "bankAccounts": [{
        "bankName": "HDFC Bank", "accountNumber": "XXXXXX4321", "ifscCode": "HDFC0000001",
        "branch": "MG Road", "isPrimary": True,
    }],
}


def ok(data):
    return {"requestId": "r", "data": data}


class TestProfileResource:
    def test_get_returns_the_unwrapped_profile(self):
        s = start_server(lambda h, i: send_json(h, 200, ok(PROFILE)))
        try:
            with HighClient(base_url=s.base_url, access_token="tok") as high:
                profile = high.profile.get()
            assert profile.clientId == "HS1234"
            assert profile.isMTFEnabled is True
            assert profile.isNRI is False
            assert profile.address.pinCode == "560001"
            assert profile.bankAccounts[0].accountNumber == "XXXXXX4321"
            assert profile.bankAccounts[0].isPrimary is True
            assert s.requests[0].method == "GET"
            assert s.requests[0].url == "/v1/profile"
        finally:
            s.close()

    async def test_async_get_returns_the_unwrapped_profile(self):
        s = start_server(lambda h, i: send_json(h, 200, ok(PROFILE)))
        try:
            async with AsyncHighClient(base_url=s.base_url, access_token="tok") as high:
                profile = await high.profile.get()
            assert profile.segmentsAllowed == ["NSE_CASH", "NSE_FNO"]
            assert s.requests[0].url == "/v1/profile"
        finally:
            s.close()
