# Feature: printer-scanner-cli, Property 1: PrinterRecord serialization round-trip
"""
Property 1: PrinterRecord serialization round-trip

For any valid PrinterRecord, serializing it to JSON via to_json() and then
deserializing via from_json() should produce a PrinterRecord that is equivalent
to the original (all fields match).

Validates: Requirements 6.4, 6.5, 6.6
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from printer_map.models import PrinterRecord


# --- Hypothesis strategies ---

# JSON-compatible leaf values (no bytes, no nan/inf, no complex nested types)
json_leaf = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**53), max_value=2**53),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=50),
)

# Recursive JSON-compatible values for raw_metadata
json_value = st.recursive(
    json_leaf,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(max_size=20), children, max_size=5),
    ),
    max_leaves=15,
)

# Strategy for color_supported / duplex_supported: bool or "unknown"
bool_or_unknown = st.one_of(st.booleans(), st.just("unknown"))

# Strategy for generating random PrinterRecord instances
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
@given(record=printer_records)
def test_printer_record_serialization_round_trip(record: PrinterRecord) -> None:
    """
    **Validates: Requirements 6.4, 6.5, 6.6**

    For any valid PrinterRecord, serializing to JSON and deserializing back
    should produce an equivalent PrinterRecord.
    """
    json_str = record.to_json()
    restored = PrinterRecord.from_json(json_str)
    assert restored == record
