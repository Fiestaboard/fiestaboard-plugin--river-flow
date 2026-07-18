"""Test fixtures for river_flow plugin."""

import pytest
from src.plugins.testing import create_mock_response


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: tests that hit the real USGS API (enable with RUN_LIVE_API_TESTS=1)",
    )


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    """Reset plugin singletons before each test."""
    yield


@pytest.fixture
def mock_api_response():
    """Fixture to create mock API responses."""
    return create_mock_response
