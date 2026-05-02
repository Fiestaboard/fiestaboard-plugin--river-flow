# River Flow Setup Guide

Display real-time streamflow data from a USGS water monitoring station.

## Overview

The River Flow plugin queries USGS Water Services for real-time discharge (streamflow) data at a configured monitoring station. It shows the current flow rate and whether the river is above or below the historical median. No API key required.

- API reference: https://waterservices.usgs.gov/

### Prerequisites

No API key required. Find your station number at waterdata.usgs.gov/nwis/rt.

## Quick Setup

1. **Enable** — Go to **Integrations** in your FiestaBoard settings and enable **River Flow**.
2. **Configure** — Fill in the plugin settings (see Configuration Reference below).
3. **Template** — Add a page using the `river_flow` plugin variables:
   ```
   {{{ river_flow.status }}}
   ```
4. **View** — Navigate to your board page to see the live display.

## Template Variables

| Variable | Description | Example |
|---|---|---|
| `river_flow.site_name` | USGS monitoring station name | `Guadalupe R nr Gilroy` |
| `river_flow.flow_cfs` | Current discharge in cubic feet per second | `245.0` |
| `river_flow.status` | Flow status relative to historical median | `Above normal` |
| `river_flow.last_updated` | Timestamp of last measurement | `2026-05-01 12:00` |

## Configuration Reference

| Setting | Name | Description | Default |
|---|---|---|---|
| `enabled` | Enabled |  | `False` |
| `site_number` | USGS Site Number | USGS monitoring station site number (e.g. 11169000 for Guadalupe River). | `11169000` |
| `refresh_seconds` | Refresh Interval (seconds) | How often to fetch streamflow data. | `900` |

## Troubleshooting

- **No data** — verify the site number and that the station is active.
- **Wrong values** — ensure the station monitors streamflow (parameter 00060).

