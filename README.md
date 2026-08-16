# Hungarian Power for Home Assistant

Custom Home Assistant integration for public Hungarian electricity-system data.

The first release targets:

- MAVIR system load (`7678`)
- MAVIR generation (`4401`)
- MAVIR fuel mix (`9404`)
- MAVIR grid frequency (`4444`)
- OAH/Paks reactor-block output

The integration uses one coordinator and a shared request budget. It deliberately
does not create one HTTP request per sensor. MAVIR's current RTDW export service
returned an explicit limit of 60 export requests per IP per hour during
development, so the default refresh interval is 15 minutes and the integration
keeps a safety margin below that limit.

## Installation

Add this repository as a custom HACS repository with category **Integration**.
After installation, restart Home Assistant and add **Hungarian Power** from
Settings → Devices & services.

No MAVIR or OAH credentials are required.

## Data sources

The current MAVIR export endpoint is:

```text
https://rtdwweb.mavir.hu/rtdwweb/webuser/chart/{chart_id}/export
```

The OAH source is the official page for the current Paks operating data:

```text
https://tranem.haea.hu/web/v3/OAHPortal.nsf/web?OpenAgent=&article=paksnpp
```

These are public web interfaces rather than stable, versioned APIs. The
integration exposes source timestamps and treats parse or rate-limit failures
as diagnosable availability problems.

## Design inspiration and attribution

This project is an independent Home Assistant implementation. The following
projects were inspected for endpoint discovery, chart mappings, parsing, and
Home Assistant patterns:

- [noherczeg/mavir-load](https://github.com/noherczeg/mavir-load)
- [adamhegyidev/energy_data_collector](https://github.com/adamhegyidev/energy_data_collector)
- [Alex-vladut7252/ro-imbalance-dashboard](https://github.com/Alex-vladut7252/ro-imbalance-dashboard)
- [Kisem/ha-mavir-stats](https://github.com/Kisem/ha-mavir-stats)
- [hikomat/dmenergy](https://github.com/hikomat/dmenergy)

The project is not affiliated with MAVIR, OAH, Paks NPP, ENTSO-E, or Home
Assistant.

## Development

```bash
uv sync --dev
uv run pytest
uv run ruff check .
```

Tests use captured or synthetic responses and do not poll the public services.

