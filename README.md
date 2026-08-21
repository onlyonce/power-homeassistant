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

## Incomplete extracts

If a source does not provide a metric during an extract cycle, the integration
keeps the last real value instead of replacing it with `unknown`. The sensor
remains available, but exposes these attributes so dashboards and automations
can detect stale data:

- `last_updated`: when the metric was last successfully extracted by the integration
- `source_timestamp`: timestamp reported by the source for that value
- `is_stale`: whether the current cycle failed to refresh the value
- `last_error`: the current extraction error, if any

The retained values and source request status are persisted in Home Assistant
storage, so they survive a Home Assistant restart or integration reload. The
integration options expose a MAVIR retry interval from 15 to 180 minutes; the
default is 60 minutes. Sensors and diagnostics also expose the source's last
attempt, last success, last HTTP status, last rate-limit event, next retry time,
and safe rate-limit response headers when the server provides them.

During development MAVIR returned HTTP 429 without `Retry-After` or
`RateLimit-*` headers. In that case the configured retry interval is used and a
shared cooldown is applied to all MAVIR charts because the observed limiter is
associated with the public client IP, not with an individual chart.

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
