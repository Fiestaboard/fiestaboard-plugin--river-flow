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
    "version": "0.1.0",
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
                "description": "USGS monitoring station site number (e.g. 11169000 for Guadalupe River).",
                "default": "11169000"
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

SAMPLE_RESPONSE = json.loads("""
{
    "value": {
        "timeSeries": [
            {
                "sourceInfo": {
                    "siteName": "Guadalupe R nr Gilroy CA",
                    "siteCode": [
                        {
                            "value": "11169000"
                        }
                    ]
                },
                "variable": {
                    "variableName": "Streamflow, ft3/s"
                },
                "values": [
                    {
                        "value": [
                            {
                                "value": "245",
                                "dateTime": "2026-05-01T12:00:00.000-07:00"
                            }
                        ]
                    }
                ]
            }
        ]
    }
}
""")


@pytest.fixture
def plugin():
    return RiverFlowPlugin(MANIFEST)


@pytest.fixture
def configured_plugin():
    p = RiverFlowPlugin(MANIFEST)
    p.config = json.loads("""
{
    "site_number": "11169000"
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
        mock_response = Mock()
        mock_response.json.return_value = SAMPLE_RESPONSE
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = configured_plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert result.data is not None
        assert "site_name" in result.data, "missing variable: site_name"
        assert "flow_cfs" in result.data, "missing variable: flow_cfs"
        assert "status" in result.data, "missing variable: status"
        assert "last_updated" in result.data, "missing variable: last_updated"

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

