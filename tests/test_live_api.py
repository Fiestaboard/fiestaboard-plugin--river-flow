"""Live tests against the real USGS Water Data API.

Disabled by default so unit runs stay fast and offline-safe.
Enable with: RUN_LIVE_API_TESTS=1 pytest tests/test_live_api.py -v
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from plugins.river_flow import RiverFlowPlugin

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE_API_TESTS") != "1",
        reason="live API tests disabled (set RUN_LIVE_API_TESTS=1)",
    ),
]

MANIFEST = json.loads((Path(__file__).parent.parent / "manifest.json").read_text())


def make_plugin(site_number: str) -> RiverFlowPlugin:
    p = RiverFlowPlugin(MANIFEST)
    p.config = {"site_number": site_number}
    return p


class TestLiveUsgsApi:

    def test_default_site_returns_current_data(self):
        site = MANIFEST["settings_schema"]["properties"]["site_number"]["default"]
        result = make_plugin(site).fetch_data()

        assert result.available is True, f"default site {site} failed: {result.error}"
        assert isinstance(result.data["flow_cfs"], float)
        assert result.data["flow_cfs"] >= 0
        assert result.data["site_name"] == "GUADALUPE R ABV HWY 101 A SAN JOSE CA"
        assert result.data["status"]

        # Reading should be recent — a stale gage means we should pick a new default
        measured = datetime.strptime(
            result.data["last_updated"], "%Y-%m-%d %H:%M"
        ).replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - measured
        assert age < timedelta(days=30), f"latest reading is {age} old"

    def test_alternate_site_returns_current_data(self):
        result = make_plugin("09380000").fetch_data()

        assert result.available is True, f"site 09380000 failed: {result.error}"
        assert "LEES FERRY" in result.data["site_name"]
        assert result.data["flow_cfs"] > 0

    def test_unknown_site_reports_no_data(self):
        result = make_plugin("00000000").fetch_data()

        assert result.available is False
        assert result.error == "No data for site"
