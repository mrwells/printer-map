"""
Unit tests for PrinterRecord dataclass.

Tests construction with defaults, to_dict/from_dict, to_json/from_json,
round-trip serialization, and edge cases.

Requirements: 6.1, 6.4, 6.5
"""

import json

from printer_map.models import PrinterRecord


# --- Fixtures: known data ---

FULL_RECORD_DATA = {
    "ip_address": "192.168.1.100",
    "hostname": "printer1.local",
    "name": "Office LaserJet",
    "protocols": ["mDNS", "SNMP"],
    "supported_formats": ["application/pdf", "image/jpeg"],
    "resolutions": ["600x600dpi", "1200x1200dpi"],
    "color_supported": True,
    "duplex_supported": False,
    "raw_metadata": {"vendor": "HP", "model": "LaserJet Pro"},
}


def _make_full_record() -> PrinterRecord:
    return PrinterRecord(**FULL_RECORD_DATA)


# --- 1. Default construction ---

class TestDefaultConstruction:
    def test_all_defaults(self):
        record = PrinterRecord()
        assert record.ip_address == ""
        assert record.hostname == ""
        assert record.name == ""
        assert record.protocols == []
        assert record.supported_formats == []
        assert record.resolutions == []
        assert record.color_supported == "unknown"
        assert record.duplex_supported == "unknown"
        assert record.raw_metadata == {}

    def test_default_lists_are_independent(self):
        """Each instance should get its own list objects."""
        a = PrinterRecord()
        b = PrinterRecord()
        a.protocols.append("mDNS")
        assert b.protocols == []


# --- 2. to_dict with fully populated record ---

class TestToDict:
    def test_to_dict_all_keys_present(self):
        record = _make_full_record()
        d = record.to_dict()
        assert set(d.keys()) == {
            "ip_address", "hostname", "name", "protocols",
            "supported_formats", "resolutions", "color_supported",
            "duplex_supported", "raw_metadata",
        }

    def test_to_dict_values_match(self):
        record = _make_full_record()
        d = record.to_dict()
        for key, value in FULL_RECORD_DATA.items():
            assert d[key] == value


# --- 3. from_dict with known data ---

class TestFromDict:
    def test_from_dict_all_fields(self):
        record = PrinterRecord.from_dict(FULL_RECORD_DATA)
        assert record.ip_address == "192.168.1.100"
        assert record.hostname == "printer1.local"
        assert record.name == "Office LaserJet"
        assert record.protocols == ["mDNS", "SNMP"]
        assert record.supported_formats == ["application/pdf", "image/jpeg"]
        assert record.resolutions == ["600x600dpi", "1200x1200dpi"]
        assert record.color_supported is True
        assert record.duplex_supported is False
        assert record.raw_metadata == {"vendor": "HP", "model": "LaserJet Pro"}

    def test_from_dict_missing_keys_uses_defaults(self):
        record = PrinterRecord.from_dict({})
        assert record.ip_address == ""
        assert record.hostname == ""
        assert record.name == ""
        assert record.protocols == []
        assert record.supported_formats == []
        assert record.resolutions == []
        assert record.color_supported == "unknown"
        assert record.duplex_supported == "unknown"
        assert record.raw_metadata == {}

    def test_from_dict_partial_data(self):
        record = PrinterRecord.from_dict({"ip_address": "10.0.0.1", "name": "Printer X"})
        assert record.ip_address == "10.0.0.1"
        assert record.name == "Printer X"
        assert record.protocols == []
        assert record.color_supported == "unknown"


# --- 4. to_json produces valid JSON ---

class TestToJson:
    def test_to_json_is_valid_json(self):
        record = _make_full_record()
        json_str = record.to_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_to_json_contains_all_fields(self):
        record = _make_full_record()
        parsed = json.loads(record.to_json())
        for key in FULL_RECORD_DATA:
            assert key in parsed


# --- 5. from_json restores record ---

class TestFromJson:
    def test_from_json_restores_record(self):
        record = _make_full_record()
        json_str = record.to_json()
        restored = PrinterRecord.from_json(json_str)
        assert restored.ip_address == "192.168.1.100"
        assert restored.name == "Office LaserJet"
        assert restored.color_supported is True
        assert restored.duplex_supported is False


# --- 6 & 7. Round-trip tests ---

class TestRoundTrip:
    def test_dict_round_trip(self):
        record = _make_full_record()
        assert PrinterRecord.from_dict(record.to_dict()) == record

    def test_json_round_trip(self):
        record = _make_full_record()
        assert PrinterRecord.from_json(record.to_json()) == record

    def test_dict_round_trip_default_record(self):
        record = PrinterRecord()
        assert PrinterRecord.from_dict(record.to_dict()) == record

    def test_json_round_trip_default_record(self):
        record = PrinterRecord()
        assert PrinterRecord.from_json(record.to_json()) == record


# --- 8. Edge cases: empty lists ---

class TestEdgeCaseEmptyLists:
    def test_empty_protocols(self):
        record = PrinterRecord(protocols=[])
        assert record.protocols == []
        d = record.to_dict()
        assert d["protocols"] == []
        assert PrinterRecord.from_dict(d).protocols == []

    def test_empty_supported_formats(self):
        record = PrinterRecord(supported_formats=[])
        assert record.supported_formats == []
        assert PrinterRecord.from_dict(record.to_dict()).supported_formats == []

    def test_empty_resolutions(self):
        record = PrinterRecord(resolutions=[])
        assert record.resolutions == []
        assert PrinterRecord.from_dict(record.to_dict()).resolutions == []


# --- 9. Edge cases: color_supported / duplex_supported variants ---

class TestEdgeCaseCapabilities:
    def test_color_supported_true(self):
        record = PrinterRecord(color_supported=True)
        assert record.color_supported is True
        assert PrinterRecord.from_json(record.to_json()).color_supported is True

    def test_color_supported_false(self):
        record = PrinterRecord(color_supported=False)
        assert record.color_supported is False
        assert PrinterRecord.from_json(record.to_json()).color_supported is False

    def test_color_supported_unknown(self):
        record = PrinterRecord(color_supported="unknown")
        assert record.color_supported == "unknown"
        assert PrinterRecord.from_json(record.to_json()).color_supported == "unknown"

    def test_duplex_supported_true(self):
        record = PrinterRecord(duplex_supported=True)
        assert record.duplex_supported is True
        assert PrinterRecord.from_json(record.to_json()).duplex_supported is True

    def test_duplex_supported_false(self):
        record = PrinterRecord(duplex_supported=False)
        assert record.duplex_supported is False
        assert PrinterRecord.from_json(record.to_json()).duplex_supported is False

    def test_duplex_supported_unknown(self):
        record = PrinterRecord(duplex_supported="unknown")
        assert record.duplex_supported == "unknown"
        assert PrinterRecord.from_json(record.to_json()).duplex_supported == "unknown"


# --- 10. Edge case: raw_metadata with nested structures ---

class TestEdgeCaseRawMetadata:
    def test_nested_dict(self):
        meta = {"level1": {"level2": {"level3": "deep"}}}
        record = PrinterRecord(raw_metadata=meta)
        restored = PrinterRecord.from_json(record.to_json())
        assert restored.raw_metadata == meta

    def test_nested_list(self):
        meta = {"tags": ["a", "b", ["nested", "list"]]}
        record = PrinterRecord(raw_metadata=meta)
        restored = PrinterRecord.from_json(record.to_json())
        assert restored.raw_metadata == meta

    def test_mixed_types(self):
        meta = {"count": 42, "active": True, "label": None, "items": [1, "two"]}
        record = PrinterRecord(raw_metadata=meta)
        restored = PrinterRecord.from_json(record.to_json())
        assert restored.raw_metadata == meta
