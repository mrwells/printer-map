"""Unit tests for scanner orchestration module."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest

from printer_map.config import ScanConfig
from printer_map.models import PrinterRecord
from printer_map.scanner import expand_targets, merge_records, run_scan, validate_targets


# --- expand_targets ---

class TestExpandTargets:
    def test_single_ip(self) -> None:
        assert expand_targets(["192.168.1.1"]) == ["192.168.1.1"]

    def test_cidr_30(self) -> None:
        result = expand_targets(["192.168.1.0/30"])
        assert result == ["192.168.1.1", "192.168.1.2"]

    def test_cidr_29(self) -> None:
        result = expand_targets(["10.0.0.0/29"])
        assert len(result) == 6
        assert "10.0.0.1" in result
        assert "10.0.0.6" in result

    def test_hostname_passthrough(self) -> None:
        result = expand_targets(["my-printer.local"])
        assert result == ["my-printer.local"]

    def test_mixed_targets(self) -> None:
        result = expand_targets(["192.168.1.1", "10.0.0.0/30", "printer.local"])
        assert result[0] == "192.168.1.1"
        assert "10.0.0.1" in result
        assert "10.0.0.2" in result
        assert "printer.local" in result


# --- merge_records ---

class TestMergeRecords:
    def test_no_overlap(self) -> None:
        r1 = PrinterRecord(ip_address="1.1.1.1", name="A", protocols=["mDNS"])
        r2 = PrinterRecord(ip_address="2.2.2.2", name="B", protocols=["SNMP"])
        merged = merge_records([r1, r2])
        assert len(merged) == 2

    def test_overlapping_ips_merge_protocols(self) -> None:
        r1 = PrinterRecord(ip_address="1.1.1.1", name="A", protocols=["mDNS"])
        r2 = PrinterRecord(ip_address="1.1.1.1", name="B", protocols=["SNMP"])
        merged = merge_records([r1, r2])
        assert len(merged) == 1
        assert set(merged[0].protocols) == {"mDNS", "SNMP"}

    def test_merge_prefers_mdns_name(self) -> None:
        r1 = PrinterRecord(ip_address="1.1.1.1", name="SNMP Name", protocols=["SNMP"])
        r2 = PrinterRecord(ip_address="1.1.1.1", name="mDNS Name", protocols=["mDNS"])
        merged = merge_records([r1, r2])
        assert merged[0].name == "mDNS Name"

    def test_merge_prefers_nonempty_hostname(self) -> None:
        r1 = PrinterRecord(ip_address="1.1.1.1", hostname="", protocols=["SNMP"])
        r2 = PrinterRecord(ip_address="1.1.1.1", hostname="printer.local", protocols=["mDNS"])
        merged = merge_records([r1, r2])
        assert merged[0].hostname == "printer.local"

    def test_merge_unions_formats_and_resolutions(self) -> None:
        r1 = PrinterRecord(
            ip_address="1.1.1.1",
            supported_formats=["application/pdf"],
            resolutions=["300x300dpi"],
            protocols=["mDNS"],
        )
        r2 = PrinterRecord(
            ip_address="1.1.1.1",
            supported_formats=["image/jpeg"],
            resolutions=["600x600dpi"],
            protocols=["SNMP"],
        )
        merged = merge_records([r1, r2])
        assert set(merged[0].supported_formats) == {"application/pdf", "image/jpeg"}
        assert set(merged[0].resolutions) == {"300x300dpi", "600x600dpi"}

    def test_merge_prefers_boolean_over_unknown(self) -> None:
        r1 = PrinterRecord(ip_address="1.1.1.1", color_supported="unknown", duplex_supported="unknown", protocols=["SNMP"])
        r2 = PrinterRecord(ip_address="1.1.1.1", color_supported=True, duplex_supported=False, protocols=["mDNS"])
        merged = merge_records([r1, r2])
        assert merged[0].color_supported is True
        assert merged[0].duplex_supported is False

    def test_empty_list(self) -> None:
        assert merge_records([]) == []


# --- run_scan orchestration ---

class TestRunScan:
    @pytest.fixture
    def sample_records(self) -> list[PrinterRecord]:
        return [
            PrinterRecord(ip_address="10.0.0.1", name="Printer A", protocols=["mDNS"]),
            PrinterRecord(ip_address="10.0.0.2", name="Printer B", protocols=["SNMP"]),
        ]

    async def test_orchestration_with_mocked_discovery(
        self, sample_records: list[PrinterRecord], capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = ScanConfig(targets=[], timeout=1.0)

        mock_mdns = AsyncMock(return_value=[sample_records[0]])
        mock_snmp = AsyncMock(return_value=[sample_records[1]])
        mock_ipp = AsyncMock(side_effect=lambda r: r)

        with (
            patch("printer_map.scanner.discover_mdns", mock_mdns),
            patch("printer_map.scanner.discover_snmp", mock_snmp),
            patch("printer_map.scanner.query_ipp_attributes", mock_ipp),
        ):
            results = await run_scan(config)

        assert len(results) == 2
        ips = {r.ip_address for r in results}
        assert ips == {"10.0.0.1", "10.0.0.2"}

    async def test_progress_reporting_to_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = ScanConfig(targets=[], timeout=1.0)

        with (
            patch("printer_map.scanner.discover_mdns", AsyncMock(return_value=[])),
            patch("printer_map.scanner.discover_snmp", AsyncMock(return_value=[])),
            patch("printer_map.scanner.query_ipp_attributes", AsyncMock(side_effect=lambda r: r)),
        ):
            await run_scan(config)

        captured = capsys.readouterr()
        assert "Phase 1" in captured.err
        assert "Phase 2" in captured.err
        assert "Phase 3" in captured.err

    async def test_no_printers_found(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = ScanConfig(targets=[], timeout=1.0)

        with (
            patch("printer_map.scanner.discover_mdns", AsyncMock(return_value=[])),
            patch("printer_map.scanner.discover_snmp", AsyncMock(return_value=[])),
        ):
            results = await run_scan(config)

        assert results == []

    async def test_invalid_target_exits_with_code_1(self) -> None:
        config = ScanConfig(targets=["not_valid!!!"], timeout=1.0)

        with pytest.raises(SystemExit) as exc_info:
            await run_scan(config)

        assert exc_info.value.code == 1

    async def test_mdns_failure_continues_with_snmp(self) -> None:
        config = ScanConfig(targets=[], timeout=1.0)
        snmp_record = PrinterRecord(ip_address="10.0.0.1", name="SNMP Printer", protocols=["SNMP"])

        async def failing_mdns(timeout: float) -> list[PrinterRecord]:
            raise ConnectionError("mDNS failed")

        with (
            patch("printer_map.scanner.discover_mdns", side_effect=failing_mdns),
            patch("printer_map.scanner.discover_snmp", AsyncMock(return_value=[snmp_record])),
            patch("printer_map.scanner.query_ipp_attributes", AsyncMock(side_effect=lambda r: r)),
        ):
            results = await run_scan(config)

        assert len(results) == 1
        assert results[0].ip_address == "10.0.0.1"
