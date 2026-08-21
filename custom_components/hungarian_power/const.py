"""Constants and metric definitions for Hungarian Power."""

from __future__ import annotations

from dataclasses import dataclass

DOMAIN = "hungarian_power"
NAME = "Hungarian Power"

CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"
CONF_MAVIR_RETRY_INTERVAL_MINUTES = "mavir_retry_interval_minutes"
DEFAULT_SCAN_INTERVAL_MINUTES = 15
MIN_SCAN_INTERVAL_MINUTES = 10
MAX_SCAN_INTERVAL_MINUTES = 60
DEFAULT_MAVIR_RETRY_INTERVAL_MINUTES = 60
MIN_MAVIR_RETRY_INTERVAL_MINUTES = 15
MAX_MAVIR_RETRY_INTERVAL_MINUTES = 180

MAVIR_BASE_URL = "https://rtdwweb.mavir.hu/rtdwweb/webuser"
OAH_URL = "https://tranem.haea.hu/web/v3/OAHPortal.nsf/web?OpenAgent=&article=paksnpp"
MAVIR_REQUEST_BUDGET = 50
MAVIR_REQUEST_WINDOW_SECONDS = 3600
MAVIR_CHART_PERIOD_MINUTES = 15
MAVIR_HISTORY_HOURS = 24
MAVIR_REQUEST_SPACING_SECONDS = 3
MAVIR_STORAGE_VERSION = 1


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """A sensor value extracted from one source series."""

    key: str
    name: str
    source: str
    chart_id: int | None
    matchers: tuple[str, ...]
    unit: str
    device_class: str
    state_class: str
    icon: str


MAVIR_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        "system_load_net",
        "Net system load",
        "MAVIR",
        7678,
        ("Nettó terhelés",),
        "MW",
        "power",
        "measurement",
        "mdi:transmission-tower",
    ),
    MetricDefinition(
        "system_load_gross_actual",
        "Gross system load actual",
        "MAVIR",
        7678,
        ("Bruttó tény rendszerterhelés",),
        "MW",
        "power",
        "measurement",
        "mdi:transmission-tower",
    ),
    MetricDefinition(
        "system_load_net_operational",
        "Net system load operational",
        "MAVIR",
        7678,
        ("Nettó rendszerterhelés tény - üzemirányítási",),
        "MW",
        "power",
        "measurement",
        "mdi:transmission-tower",
    ),
    MetricDefinition(
        "system_load_day_ahead",
        "System load day-ahead estimate",
        "MAVIR",
        7678,
        ("Bruttó rendszerterhelés becslés (dayahead)",),
        "MW",
        "power",
        "measurement",
        "mdi:chart-line",
    ),
    MetricDefinition(
        "generation_gross_actual",
        "Gross generation actual",
        "MAVIR",
        4401,
        ("Bruttó tény erőművi termelés",),
        "MW",
        "power",
        "measurement",
        "mdi:factory",
    ),
    MetricDefinition(
        "generation_gross_plan",
        "Gross generation plan",
        "MAVIR",
        4401,
        ("Bruttó terv erőművi termelés",),
        "MW",
        "power",
        "measurement",
        "mdi:chart-line",
    ),
    MetricDefinition(
        "generation_net_actual",
        "Net domestic generation actual",
        "MAVIR",
        4401,
        ("Nettó hazai termelés tény",),
        "MW",
        "power",
        "measurement",
        "mdi:factory",
    ),
    MetricDefinition(
        "fuel_nuclear",
        "Nuclear generation",
        "MAVIR",
        9404,
        ("Nukleár",),
        "MW",
        "power",
        "measurement",
        "mdi:atom",
    ),
    MetricDefinition(
        "fuel_lignite",
        "Lignite generation",
        "MAVIR",
        9404,
        ("Lignit",),
        "MW",
        "power",
        "measurement",
        "mdi:factory",
    ),
    MetricDefinition(
        "fuel_gas",
        "Gas generation",
        "MAVIR",
        9404,
        ("Földgáz", "Gázerőmű"),
        "MW",
        "power",
        "measurement",
        "mdi:gas-burner",
    ),
    MetricDefinition(
        "fuel_hard_coal",
        "Hard-coal generation",
        "MAVIR",
        9404,
        ("Kőszén", "Kemény szén"),
        "MW",
        "power",
        "measurement",
        "mdi:factory",
    ),
    MetricDefinition(
        "fuel_wind",
        "Wind generation",
        "MAVIR",
        9404,
        ("Szélerőmű", "Szélenergia"),
        "MW",
        "power",
        "measurement",
        "mdi:wind-turbine",
    ),
    MetricDefinition(
        "fuel_industrial_pv",
        "Industrial PV generation",
        "MAVIR",
        9404,
        ("Ipari PV", "Ipari naperőmű"),
        "MW",
        "power",
        "measurement",
        "mdi:solar-power",
    ),
    MetricDefinition(
        "fuel_biomass",
        "Biomass generation",
        "MAVIR",
        9404,
        ("Biomassza",),
        "MW",
        "power",
        "measurement",
        "mdi:leaf",
    ),
    MetricDefinition(
        "fuel_run_of_river_hydro",
        "Run-of-river hydro generation",
        "MAVIR",
        9404,
        ("Folyóvízi", "Folyóvíz"),
        "MW",
        "power",
        "measurement",
        "mdi:water",
    ),
    MetricDefinition(
        "fuel_reservoir_hydro",
        "Reservoir hydro generation",
        "MAVIR",
        9404,
        ("Tározós",),
        "MW",
        "power",
        "measurement",
        "mdi:water",
    ),
    MetricDefinition(
        "grid_frequency",
        "Grid frequency",
        "MAVIR",
        4444,
        ("Hálózati frekvencia",),
        "Hz",
        "frequency",
        "measurement",
        "mdi:sine-wave",
    ),
)


OAH_METRICS: tuple[MetricDefinition, ...] = tuple(
    MetricDefinition(
        f"paks_unit_{unit}",
        f"Paks block {unit}",
        "OAH",
        None,
        (),
        "MW",
        "power",
        "measurement",
        "mdi:atom",
    )
    for unit in range(1, 5)
)

ALL_METRICS = MAVIR_METRICS + OAH_METRICS
METRICS_BY_KEY = {metric.key: metric for metric in ALL_METRICS}
