"""Tests for the river_flow plugin."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, Mock

import pytest

from plugins.river_flow import RiverFlowPlugin
from src.plugins.base import PluginResult

MANIFEST = json.loads("""
{
    "id": "river_flow",
    "name": "River Flow",
    "version": "0.2.0",
    "settings_schema": {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "title": "Enabled",
                "default": false
            },
            "site_number": {
                "type": "string",
                "title": "USGS Site Number",
                "description": "USGS monitoring station site number (e.g. 11169025 for Guadalupe River).",
                "default": "11169025"
            },
            "refresh_seconds": {
                "type": "integer",
                "title": "Refresh Interval (seconds)",
                "description": "How often to fetch streamflow data.",
                "default": 900,
                "minimum": 600
            }
        },
        "required": [
            "site_number"
        ]
    }
}
""")

# GeoJSON FeatureCollection from /ogcapi/v0/collections/latest-continuous/items
LATEST_RESPONSE = json.loads("""
{
    "type": "FeatureCollection",
    "numberReturned": 1,
    "features": [
        {
            "type": "Feature",
            "id": "0a5f45d6-1b4d-4b1e-9f5e-000000000001",
            "geometry": {
                "type": "Point",
                "coordinates": [-121.9346, 37.3113]
            },
            "properties": {
                "time_series_id": "0a5f45d6-1b4d-4b1e-9f5e-000000000001",
                "monitoring_location_id": "USGS-11169025",
                "parameter_code": "00060",
                "statistic_id": "00011",
                "time": "2026-05-01T19:00:00+00:00",
                "value": 245.0,
                "unit_of_measure": "ft^3/s",
                "approval_status": "Provisional",
                "qualifier": null,
                "last_modified": "2026-05-01T19:05:00+00:00"
            }
        }
    ]
}
""")

# Feature from /ogcapi/v0/collections/monitoring-locations/items/USGS-11169025
SITE_RESPONSE = json.loads("""
{
    "type": "Feature",
    "id": "USGS-11169025",
    "geometry": {
        "type": "Point",
        "coordinates": [-121.9346, 37.3113]
    },
    "properties": {
        "agency_code": "USGS",
        "monitoring_location_number": "11169025",
        "monitoring_location_name": "GUADALUPE R ABV HWY 101 A SAN JOSE CA",
        "state_code": "06",
        "site_type_code": "ST"
    }
}
""")


def mock_api(latest=LATEST_RESPONSE, site=SITE_RESPONSE):
    """Return a requests.get side_effect that dispatches on the new API URLs."""

    def _get(url, **kwargs):
        resp = Mock()
        resp.raise_for_status = Mock()
        if "latest-continuous" in url:
            resp.json.return_value = latest
        elif "monitoring-locations" in url:
            resp.json.return_value = site
        else:
            raise AssertionError(f"Unexpected URL requested: {url}")
        return resp

    return _get


@pytest.fixture
def plugin():
    return RiverFlowPlugin(MANIFEST)


@pytest.fixture
def configured_plugin():
    p = RiverFlowPlugin(MANIFEST)
    p.config = json.loads("""
{
    "site_number": "11169025"
}
""")
    return p


class TestRiverFlowPlugin:

    def test_plugin_id(self, plugin):
        assert plugin.plugin_id == "river_flow"

    def test_manifest_valid(self):
        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            m = json.load(f)
        for field in ("id", "name", "version"):
            assert field in m

    @patch("plugins.river_flow.requests.get")
    def test_fetch_data_success(self, mock_get, configured_plugin):
        mock_get.side_effect = mock_api()

        result = configured_plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data is not None
        assert result.data["site_name"] == "GUADALUPE R ABV HWY 101 A SAN JOSE CA"
        assert result.data["flow_cfs"] == 245.0
        assert result.data["status"] == "Near normal"
        assert result.data["last_updated"] == "2026-05-01 19:00"

    @patch("plugins.river_flow.requests.get")
    def test_requests_use_new_api_with_user_agent(self, mock_get, configured_plugin):
        mock_get.side_effect = mock_api()

        configured_plugin.fetch_data()

        assert mock_get.call_count >= 1
        for call in mock_get.call_args_list:
            url = call.args[0] if call.args else call.kwargs["url"]
            assert url.startswith("https://api.waterdata.usgs.gov/")
            headers = call.kwargs.get("headers", {})
            assert "FiestaBoard River Flow Plugin" in headers.get("User-Agent", "")

    @patch("plugins.river_flow.requests.get")
    def test_fetch_data_no_features(self, mock_get, configured_plugin):
        empty = {"type": "FeatureCollection", "numberReturned": 0, "features": []}
        mock_get.side_effect = mock_api(latest=empty)

        result = configured_plugin.fetch_data()

        assert result.available is False
        assert result.error == "No data for site"

    @patch("plugins.river_flow.requests.get")
    def test_fetch_data_null_value(self, mock_get, configured_plugin):
        latest = json.loads(json.dumps(LATEST_RESPONSE))
        latest["features"][0]["properties"]["value"] = None
        mock_get.side_effect = mock_api(latest=latest)

        result = configured_plugin.fetch_data()

        assert result.available is False
        assert result.error == "No discharge values"

    @patch("plugins.river_flow.requests.get")
    def test_fetch_data_picks_most_recent_feature(self, mock_get, configured_plugin):
        latest = json.loads(json.dumps(LATEST_RESPONSE))
        older = json.loads(json.dumps(latest["features"][0]))
        older["properties"]["time"] = "2026-05-01T17:30:00+00:00"
        older["properties"]["value"] = 99.0
        latest["features"].insert(0, older)
        latest["numberReturned"] = 2
        mock_get.side_effect = mock_api(latest=latest)

        result = configured_plugin.fetch_data()

        assert result.available is True
        assert result.data["flow_cfs"] == 245.0
        assert result.data["last_updated"] == "2026-05-01 19:00"

    @patch("plugins.river_flow.requests.get")
    def test_site_name_lookup_failure_falls_back_to_site_number(
        self, mock_get, configured_plugin
    ):
        def _get(url, **kwargs):
            if "monitoring-locations" in url:
                import requests as req_mod

                raise req_mod.exceptions.ConnectionError("site lookup down")
            return mock_api()(url, **kwargs)

        mock_get.side_effect = _get

        result = configured_plugin.fetch_data()

        assert result.available is True
        assert result.data["site_name"] == "11169025"
        assert result.data["flow_cfs"] == 245.0

    @patch("plugins.river_flow.requests.get")
    def test_site_name_cached_across_fetches(self, mock_get, configured_plugin):
        mock_get.side_effect = mock_api()

        configured_plugin.fetch_data()
        configured_plugin.fetch_data()

        urls = [
            call.args[0] if call.args else call.kwargs["url"]
            for call in mock_get.call_args_list
        ]
        assert len([u for u in urls if "latest-continuous" in u]) == 2
        assert len([u for u in urls if "monitoring-locations" in u]) == 1

    @patch("plugins.river_flow.requests.get")
    def test_fetch_data_network_error(self, mock_get, configured_plugin):
        import requests as req_mod
        mock_get.side_effect = req_mod.exceptions.ConnectionError("network down")

        result = configured_plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    @patch("plugins.river_flow.requests.get")
    def test_fetch_data_bad_json(self, mock_get, configured_plugin):
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("bad json")
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = configured_plugin.fetch_data()

        assert result.available is False
