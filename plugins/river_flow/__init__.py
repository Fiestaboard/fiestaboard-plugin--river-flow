"""Display real-time streamflow data from a USGS water monitoring station."""

from __future__ import annotations

import logging
from typing import Any, Dict, List
import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

# USGS Water Data OGC API (legacy waterservices.usgs.gov is decommissioned Q1 2027)
LATEST_URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/latest-continuous/items"
SITE_URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/monitoring-locations/items/{location_id}"
USER_AGENT = "FiestaBoard River Flow Plugin (https://github.com/Fiestaboard/fiestaboard-plugin--river-flow)"


class RiverFlowPlugin(PluginBase):
    """River Flow plugin for FiestaBoard."""

    @property
    def plugin_id(self) -> str:
        return "river_flow"

    def _headers(self) -> Dict[str, str]:
        headers = {"User-Agent": USER_AGENT}
        api_key = self.config.get("api_key")
        if api_key:
            headers["X-Api-Key"] = api_key
        return headers

    def _site_name(self, site: str, location_id: str) -> str:
        """Look up the station name, cached per site (names are static)."""
        cache = getattr(self, "_site_names", None)
        if cache is None:
            cache = self._site_names = {}
        if site in cache:
            return cache[site]
        try:
            response = requests.get(
                SITE_URL.format(location_id=location_id),
                params={"f": "json"},
                headers=self._headers(),
                timeout=10,
            )
            response.raise_for_status()
            name = str(response.json()["properties"]["monitoring_location_name"])
            cache[site] = name
            return name
        except Exception:
            # Name is cosmetic; fall back to the site number and retry next refresh
            logger.warning("Could not fetch site name for %s", site, exc_info=True)
            return site

    def fetch_data(self) -> PluginResult:
        try:
            # 11169025 = Guadalupe R abv Hwy 101 at San Jose (11169000 stopped reporting in 2003)
            site = self.config.get("site_number") or "11169025"
            location_id = f"USGS-{site}"

            response = requests.get(
                LATEST_URL,
                params={
                    "monitoring_location_id": location_id,
                    "parameter_code": "00060",  # discharge in cfs
                    "f": "json",
                },
                headers=self._headers(),
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            features = data.get("features", [])
            if not features:
                return PluginResult(available=False, error="No data for site")

            # One feature per observation; take the most recent reading
            latest = max(
                features, key=lambda f: f.get("properties", {}).get("time") or ""
            )
            props = latest.get("properties", {})
            if props.get("value") is None:
                return PluginResult(available=False, error="No discharge values")

            flow_cfs = round(float(props["value"]), 1)
            # `time` is ISO 8601 UTC (the legacy API returned station-local time)
            dt_str = str(props.get("time", ""))[:16].replace("T", " ")

            site_name = self._site_name(site, location_id)

            # Simple status heuristic
            if flow_cfs > 5000:
                status = "Flood stage"
            elif flow_cfs > 1000:
                status = "Above normal"
            elif flow_cfs > 100:
                status = "Near normal"
            elif flow_cfs > 10:
                status = "Below normal"
            else:
                status = "Very low"

            return PluginResult(
                available=True,
                data={
                    "site_name": site_name,
                    "flow_cfs": flow_cfs,
                    "status": status,
                    "last_updated": dt_str,
                },
            )
        except Exception as e:
            logger.exception("Error fetching river flow data")
            return PluginResult(available=False, error=str(e))

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors = []
        if not config.get("site_number"):
            errors.append("site_number is required")
        return errors

    def cleanup(self) -> None:
        pass
