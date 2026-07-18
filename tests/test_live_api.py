"""Live tests against the real USGS Water Data API.

Disabled by default so unit runs stay fast and offline-safe.
Enable with: RUN_LIVE_API_TESTS=1 pytest tests/test_live_api.py -v

TestLiveUsgsApi exercises the plugin end-to-end; TestApiContract pins the
exact API surface the plugin depends on, so if USGS drops or renames an
endpoint, query parameter, or response field, the weekly canary names the
specific break instead of a vague plugin failure.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from plugins.river_flow import LATEST_URL, SITE_URL, USER_AGENT, RiverFlowPlugin

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

    @pytest.mark.parametrize(
        "site",
        [
            "01646500",  # Potomac River near Washington, DC
            "07374000",  # Mississippi River at Baton Rouge, LA
            "14211720",  # Willamette River at Portland, OR (tidal: flow can be negative)
        ],
    )
    def test_gages_across_regions(self, site):
        result = make_plugin(site).fetch_data()

        assert result.available is True, f"site {site} failed: {result.error}"
        assert isinstance(result.data["flow_cfs"], float)
        assert result.data["site_name"] != site, "site name lookup fell back"


class TestApiContract:
    """Pin the API surface the plugin depends on, independent of plugin logic."""

    def _get(self, url, params):
        resp = requests.get(
            url, params=params, headers={"User-Agent": USER_AGENT}, timeout=10
        )
        assert resp.status_code == 200, f"{url} returned {resp.status_code}"
        return resp.json()

    def test_latest_continuous_shape(self):
        data = self._get(
            LATEST_URL,
            {
                "monitoring_location_id": "USGS-01646500",
                "parameter_code": "00060",
                "f": "json",
            },
        )

        assert data.get("type") == "FeatureCollection"
        features = data.get("features")
        assert features, "no features for a major active gage (Potomac)"

        props = features[0].get("properties", {})
        # Every field fetch_data reads must still exist
        for field in ("value", "time", "parameter_code", "monitoring_location_id"):
            assert field in props, f"API dropped properties.{field}"

        assert float(props["value"]) == float(props["value"])  # coercible, not NaN
        # `time` must stay ISO 8601 so the [:16] slice yields "YYYY-MM-DD HH:MM"
        datetime.fromisoformat(props["time"])
        assert props["parameter_code"] == "00060", "parameter_code filter not honored"
        assert props["monitoring_location_id"] == "USGS-01646500"

    def test_latest_continuous_unknown_site_returns_empty_not_error(self):
        # fetch_data's "No data for site" path relies on 200 + empty features
        data = self._get(
            LATEST_URL,
            {
                "monitoring_location_id": "USGS-00000000",
                "parameter_code": "00060",
                "f": "json",
            },
        )

        assert data.get("type") == "FeatureCollection"
        assert data.get("features") == []

    def test_monitoring_locations_shape(self):
        data = self._get(
            SITE_URL.format(location_id="USGS-01646500"), {"f": "json"}
        )

        props = data.get("properties", {})
        name = props.get("monitoring_location_name")
        assert isinstance(name, str) and name.strip(), (
            "API dropped properties.monitoring_location_name"
        )
        assert props.get("monitoring_location_number") == "01646500"
