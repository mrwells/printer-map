"""Unit tests for the formatters module."""

import csv
import io
import json

import pytest

from printer_map.formatters import (
    COLUMNS,
    format_csv,
    format_json,
    format_output,
    format_table,
)
from printer_map.models import PrinterRecord


def _sample_record(**overrides) -> PrinterRecord:
    defaults = {
        "ip_address": "192.168.1.10",
        "hostname": "printer1.local",
        "name": "Office Printer",
        "protocols": ["mDNS", "SNMP"],
        "supported_formats": ["application/pdf", "image/jpeg"],
        "resolutions": ["600x600dpi"],
        "color_supported": True,
        "duplex_supported": False,
    }
    defaults.update(overrides)
    return PrinterRecord(**defaults)


# --- format_table ---

class TestFormatTable:
    def test_single_record(self):
        record = _sample_record()
        output = format_table([record])
        # Card-style output contains all fields
        assert "192.168.1.10" in output
        assert "Office Printer" in output
        assert "mDNS, SNMP" in output
        assert "application/pdf, image/jpeg" in output
        assert "600x600dpi" in output
        assert "True" in output
        assert "False" in output

    def test_empty_records(self):
        output = format_table([])
        assert output == ""

    def test_multiple_records_separated(self):
        r1 = _sample_record(ip_address="10.0.0.1", name="Short")
        r2 = _sample_record(ip_address="192.168.100.200", name="A Much Longer Printer Name")
        output = format_table([r1, r2])
        # Both printers appear
        assert "10.0.0.1" in output
        assert "192.168.100.200" in output
        assert "Short" in output
        assert "A Much Longer Printer Name" in output
        # Blocks are separated by a blank line
        assert "\n\n" in output


# --- format_json ---

class TestFormatJson:
    def test_single_record(self):
        record = _sample_record()
        output = format_json([record])
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["ip_address"] == "192.168.1.10"
        assert parsed[0]["name"] == "Office Printer"

    def test_empty_records(self):
        output = format_json([])
        assert output == "[]"

    def test_valid_json(self):
        records = [_sample_record(), _sample_record(ip_address="10.0.0.5", name="Second")]
        output = format_json(records)
        parsed = json.loads(output)
        assert len(parsed) == 2


# --- format_csv ---

class TestFormatCsv:
    def test_single_record(self):
        record = _sample_record()
        output = format_csv([record])
        reader = csv.reader(io.StringIO(output))
        rows = list(reader)
        assert rows[0] == COLUMNS
        assert len(rows) == 2  # header + 1 data row
        assert rows[1][0] == "192.168.1.10"

    def test_empty_records(self):
        output = format_csv([])
        reader = csv.reader(io.StringIO(output))
        rows = list(reader)
        assert len(rows) == 1  # header only
        assert rows[0] == COLUMNS

    def test_row_count(self):
        records = [_sample_record(ip_address=f"10.0.0.{i}") for i in range(5)]
        output = format_csv(records)
        reader = csv.reader(io.StringIO(output))
        rows = list(reader)
        assert len(rows) == 6  # header + 5 data rows


# --- format_output ---

class TestFormatOutput:
    def test_dispatches_table(self):
        record = _sample_record()
        output = format_output([record], "table")
        assert "192.168.1.10" in output
        assert "Office Printer" in output

    def test_dispatches_json(self):
        record = _sample_record()
        output = format_output([record], "json")
        parsed = json.loads(output)
        assert len(parsed) == 1

    def test_dispatches_csv(self):
        record = _sample_record()
        output = format_output([record], "csv")
        assert "IP,Name,Protocols" in output

    def test_unknown_format_raises(self):
        with pytest.raises(ValueError, match="Unknown output format"):
            format_output([], "xml")
