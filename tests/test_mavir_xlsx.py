from io import BytesIO

from openpyxl import Workbook

from custom_components.hungarian_power.mavir_xlsx import parse_mavir_xlsx


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
