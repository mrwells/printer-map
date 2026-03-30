# Feature: printer-scanner-cli, Property 2: JSON formatter round-trip
"""
Property 2: JSON formatter round-trip

For any list of valid PrinterRecord objects, formatting them as JSON via
format_json() should produce a valid JSON string that, when parsed back into
a list of dicts and re-formatted, produces an identical JSON string.
Additionally, the parsed JSON array should contain exactly one object per
input record.

Validates: Requirements 5.3, 5.5
"""

import csv
import io
import json

from hypothesis import given, settings
from hypothesis import strategies as st

from printer_map.formatters import format_csv, format_json
from printer_map.models import PrinterRecord

# --- Hypothesis strategies (same pattern as test_model_properties.py) ---

json_leaf = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**53), max_value=2**53),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=50),
)

json_value = st.recursive(
    json_leaf,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=20), children, max_size=5),
    ),
    max_leaves=15,
)

bool_or_unknown = st.one_of(st.booleans(), st.just("unknown"))

printer_records = st.builds(
    PrinterRecord,
    ip_address=st.text(max_size=45),
    hostname=st.text(max_size=100),
    name=st.text(max_size=100),
    protocols=st.lists(st.text(max_size=30), max_size=5),
    supported_formats=st.lists(st.text(max_size=50), max_size=5),
    resolutions=st.lists(st.text(max_size=20), max_size=5),
    color_supported=bool_or_unknown,
    duplex_supported=bool_or_unknown,
    raw_metadata=st.dictionaries(st.text(max_size=20), json_value, max_size=5),
)


@settings(max_examples=100)
@given(records=st.lists(printer_records, max_size=10))
def test_json_formatter_round_trip(records: list[PrinterRecord]) -> None:
    """
    **Validates: Requirements 5.3, 5.5**

    For any list of PrinterRecord objects, format_json() output should parse
    back to equivalent data and re-format identically (idempotency).
    """
    json_output = format_json(records)

    # Parse the JSON string back
    parsed = json.loads(json_output)

    # The parsed list should have the same length as the input
    assert len(parsed) == len(records)

    # Re-format the parsed data and assert idempotency
    re_formatted = json.dumps(parsed, indent=2)
    assert re_formatted == json_output

    # Each parsed dict should match the corresponding record's to_dict()
    for parsed_dict, record in zip(parsed, records):
        assert parsed_dict == record.to_dict()


# Feature: printer-scanner-cli, Property 8: Table output contains all record fields


@settings(max_examples=100)
@given(records=st.lists(printer_records, min_size=1, max_size=10))
def test_table_output_contains_all_record_fields(records: list[PrinterRecord]) -> None:
    """
    **Validates: Requirements 5.2**

    For any non-empty list of PrinterRecord objects, the table-formatted output
    should contain the ip_address, name, and at least one protocol for every
    record in the input list.
    """
    from printer_map.formatters import format_table

    table_output = format_table(records)

    for record in records:
        assert record.ip_address in table_output
        assert record.name in table_output
        if record.protocols:
            assert any(proto in table_output for proto in record.protocols)


# Feature: printer-scanner-cli, Property 9: CSV output has header and correct row count


@settings(max_examples=100)
@given(records=st.lists(printer_records, max_size=10))
def test_csv_output_has_header_and_correct_row_count(records: list[PrinterRecord]) -> None:
    """
    **Validates: Requirements 5.4**

    For any list of PrinterRecord objects, the CSV-formatted output should have
    exactly len(records) + 1 lines (one header row plus one data row per record),
    and the header row should contain the correct column names.
    """
    csv_output = format_csv(records)

    # Parse the CSV output
    reader = csv.reader(io.StringIO(csv_output))
    rows = list(reader)

    # Assert row count: header + one row per record
    assert len(rows) == len(records) + 1

    # Assert header columns
    assert rows[0] == ["IP", "Name", "Protocols", "Formats", "Resolution", "Color", "Duplex"]
