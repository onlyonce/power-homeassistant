from custom_components.hungarian_power.oah_html import parse_oah_html


def test_parse_oah_page() -> None:
    html = """
    <table>
      <tr><td>Mérés dátuma:</td><td>2026. 08. 16 17:09</td></tr>
      <tr><th>1. blokk</th><th>2. blokk</th><th>3. blokk</th><th>4. blokk</th></tr>
      <tr><td>0 MW</td><td>481 MW</td><td>0 MW</td><td>0 MW</td></tr>
    </table>
    """

    result = parse_oah_html(html)

    assert result.units_mw == (0.0, 481.0, 0.0, 0.0)
    assert result.timestamp.hour == 17
    assert result.timestamp.minute == 9

