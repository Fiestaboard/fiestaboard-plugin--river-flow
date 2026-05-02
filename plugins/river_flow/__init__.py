"""Display real-time streamflow data from a USGS water monitoring station."""

from __future__ import annotations

import logging
from typing import Any, Dict, List
import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)

API_URL = "https://waterservices.usgs.gov/nwis/iv/"
USER_AGENT = "FiestaBoard River Flow Plugin (https://github.com/Fiestaboard/fiestaboard-plugin--river-flow)"


class RiverFlowPlugin(PluginBase):
    """River Flow plugin for FiestaBoard."""

    @property
    def plugin_id(self) -> str:
        return "river_flow"

    def fetch_data(self) -> PluginResult:
        try:
            site = self.config.get("site_number") or "11169000"

            response = requests.get(
                API_URL,
                params={
                    "format": "json",
                    "sites": site,
                    "parameterCd": "00060",  # discharge in cfs
                    "siteStatus": "active",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            time_series = data.get("value", {}).get("timeSeries", [])
            if not time_series:
                return PluginResult(available=False, error="No data for site")

            ts = time_series[0]
            site_name = str(ts.get("sourceInfo", {}).get("siteName", site))[:22]

            values = ts.get("values", [{}])[0].get("value", [])
            if not values:
                return PluginResult(available=False, error="No discharge values")

            latest = values[-1]
            flow_cfs = round(float(latest.get("value", 0)), 1)
            dt_str = latest.get("dateTime", "")[:16].replace("T", " ")

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
