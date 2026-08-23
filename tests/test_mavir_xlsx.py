from io import BytesIO

from openpyxl import Workbook

from custom_components.hungarian_power.const import ALL_METRICS, MAVIR_METRICS
from custom_components.hungarian_power.mavir_xlsx import parse_mavir_xlsx
from custom_components.hungarian_power.models import MavirChartData


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Időpont", "Nettó terhelés", "Hálózati frekvencia"])
    sheet.append(["2026.08.16 10:00:00 +0200", 3673.032, 50.01])
    sheet.append(["2026.08.16 10:15:00 +0200", None, 50.02])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_parse_mavir_xlsx_uses_latest_non_null_value() -> None:
    result = parse_mavir_xlsx(_workbook_bytes(), 7678)

    assert result.chart_id == 7678
    assert result.point_count == 2
    assert result.value_for(("Nettó terhelés",)) == (
        3673.032,
        result.column_timestamps["Nettó terhelés"],
    )
    assert result.value_for(("Hálózati frekvencia",))[0] == 50.02


def test_current_9404_gas_heading_matches_metric_definition() -> None:
    definition = next(metric for metric in MAVIR_METRICS if metric.key == "fuel_gas")
    timestamp = parse_mavir_xlsx(_workbook_bytes(), 9404).timestamp
    assert timestamp is not None
    chart = MavirChartData(
        chart_id=9404,
        timestamp=timestamp,
        columns={"Gáz (fosszilis) erőművek": 203.5},
        column_timestamps={"Gáz (fosszilis) erőművek": timestamp},
        point_count=1,
    )

    assert chart.value_for(definition.matchers) == (203.5, timestamp)


def test_current_9404_run_of_river_heading_matches_metric_definition() -> None:
    definition = next(metric for metric in MAVIR_METRICS if metric.key == "fuel_run_of_river_hydro")
    timestamp = parse_mavir_xlsx(_workbook_bytes(), 9404).timestamp
    assert timestamp is not None
    chart = MavirChartData(
        chart_id=9404,
        timestamp=timestamp,
        columns={"Folyóvizes erőművek": 4.2},
        column_timestamps={"Folyóvizes erőművek": timestamp},
        point_count=1,
    )

    assert chart.value_for(definition.matchers) == (4.2, timestamp)


def test_exposed_metrics_exclude_retired_oah_block_entities() -> None:
    assert all(not metric.key.startswith("paks_unit_") for metric in ALL_METRICS)
