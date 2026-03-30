"""
Unit tests for SNMP discovery module.

Tests SNMP query with mocked pysnmp responses, timeout/skip behavior
for non-responding hosts, and community string usage.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from printer_map.snmp_discovery import (
    OID_HR_DEVICE_DESCR,
    OID_PRT_GENERAL_PRINTER_NAME,
    _query_host,
    discover_snmp,
)
from printer_map.models import PrinterRecord


# --- Helpers ---

def _make_var_binds(device_descr: str = "HP LaserJet", printer_name: str = "Office Printer"):
    """Create mock SNMP var_binds tuple."""
    oid_descr = MagicMock()
    oid_descr.__str__ = lambda self: OID_HR_DEVICE_DESCR
    val_descr = MagicMock()
    val_descr.__str__ = lambda self: device_descr
    val_descr.__bool__ = lambda self: bool(device_descr)

    oid_name = MagicMock()
    oid_name.__str__ = lambda self: OID_PRT_GENERAL_PRINTER_NAME
    val_name = MagicMock()
    val_name.__str__ = lambda self: printer_name
    val_name.__bool__ = lambda self: bool(printer_name)

    return ((oid_descr, val_descr), (oid_name, val_name))


def _patch_snmp(
    error_indication=None,
    error_status=0,
    var_binds=None,
    transport_side_effect=None,
    get_cmd_side_effect=None,
):
    """Return a dict of context managers that patch pysnmp internals."""
    if var_binds is None:
        var_binds = _make_var_binds()

    mock_transport_instance = AsyncMock()

    mock_transport_cls = MagicMock()
    if transport_side_effect:
        mock_transport_cls.create = AsyncMock(side_effect=transport_side_effect)
    else:
        mock_transport_cls.create = AsyncMock(return_value=mock_transport_instance)

    patches = {
        "transport": patch(
            "printer_map.snmp_discovery.UdpTransportTarget",
            mock_transport_cls,
        ),
        "get_cmd": patch(
            "printer_map.snmp_discovery.get_cmd",
            new_callable=AsyncMock,
            side_effect=get_cmd_side_effect,
            return_value=(error_indication, error_status, 0, var_binds),
        ),
        "engine": patch(
            "printer_map.snmp_discovery.SnmpEngine",
            return_value=MagicMock(),
        ),
    }
    return patches


# --- _query_host ---

class TestQueryHost:
    async def test_returns_record_on_success(self) -> None:
        """A responding host returns a PrinterRecord."""
        var_binds = _make_var_binds("HP LaserJet 4000", "Office Printer")
        patches = _patch_snmp(var_binds=var_binds)

        with patches["transport"], patches["get_cmd"], patches["engine"]:
            engine = MagicMock()
            record = await _query_host(engine, "192.168.1.50", "public", 5.0)

        assert record is not None
        assert record.ip_address == "192.168.1.50"
        assert record.protocols == ["SNMP"]
        assert record.name == "Office Printer"

    async def test_returns_none_on_timeout(self) -> None:
        """A non-responding host (error_indication set) returns None."""
        patches = _patch_snmp(error_indication="No SNMP response received before timeout")

        with patches["transport"], patches["get_cmd"], patches["engine"]:
            engine = MagicMock()
            record = await _query_host(engine, "192.168.1.99", "public", 2.0)

        assert record is None

    async def test_returns_none_on_error_status(self) -> None:
        """An SNMP error status returns None."""
        patches = _patch_snmp(error_status=2)

        with patches["transport"], patches["get_cmd"], patches["engine"]:
            engine = MagicMock()
            record = await _query_host(engine, "192.168.1.99", "public", 2.0)

        assert record is None

    async def test_returns_none_on_transport_failure(self) -> None:
        """If transport creation fails, returns None."""
        patches = _patch_snmp(transport_side_effect=OSError("Network error"))

        with patches["transport"], patches["get_cmd"], patches["engine"]:
            engine = MagicMock()
            record = await _query_host(engine, "10.0.0.1", "public", 2.0)

        assert record is None

    async def test_returns_none_on_get_cmd_exception(self) -> None:
        """If get_cmd raises, returns None."""
        patches = _patch_snmp(get_cmd_side_effect=Exception("SNMP internal error"))

        with patches["transport"], patches["get_cmd"], patches["engine"]:
            engine = MagicMock()
            record = await _query_host(engine, "10.0.0.1", "public", 2.0)

        assert record is None

    async def test_uses_device_descr_when_no_printer_name(self) -> None:
        """Falls back to hrDeviceDescr when prtGeneralPrinterName is empty."""
        var_binds = _make_var_binds("HP LaserJet 4000", "")
        patches = _patch_snmp(var_binds=var_binds)

        with patches["transport"], patches["get_cmd"], patches["engine"]:
            engine = MagicMock()
            record = await _query_host(engine, "192.168.1.50", "public", 5.0)

        assert record is not None
        assert record.name == "HP LaserJet 4000"

    async def test_raw_metadata_contains_oid_values(self) -> None:
        """raw_metadata stores the OID string values."""
        var_binds = _make_var_binds("LaserJet", "MyPrinter")
        patches = _patch_snmp(var_binds=var_binds)

        with patches["transport"], patches["get_cmd"], patches["engine"]:
            engine = MagicMock()
            record = await _query_host(engine, "192.168.1.50", "public", 5.0)

        assert record is not None
        assert OID_HR_DEVICE_DESCR in record.raw_metadata
        assert record.raw_metadata[OID_HR_DEVICE_DESCR] == "LaserJet"
        assert OID_PRT_GENERAL_PRINTER_NAME in record.raw_metadata
        assert record.raw_metadata[OID_PRT_GENERAL_PRINTER_NAME] == "MyPrinter"


# --- discover_snmp ---

class TestDiscoverSnmp:
    async def test_returns_records_for_responding_hosts(self) -> None:
        """Hosts that respond produce PrinterRecords."""
        var_binds = _make_var_binds("Printer A", "PrinterA")
        patches = _patch_snmp(var_binds=var_binds)

        with patches["transport"], patches["get_cmd"], patches["engine"]:
            result = await discover_snmp(
                targets=["192.168.1.10", "192.168.1.11"],
                community="public",
                timeout=2.0,
            )

        assert len(result) == 2
        assert all(isinstance(r, PrinterRecord) for r in result)
        assert result[0].ip_address == "192.168.1.10"
        assert result[1].ip_address == "192.168.1.11"

    async def test_skips_non_responding_hosts(self) -> None:
        """Non-responding hosts are skipped, responding ones are returned."""
        var_binds = _make_var_binds("Printer", "GoodPrinter")

        call_count = 0

        async def alternating_get_cmd(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First host times out
                return ("No SNMP response received before timeout", 0, 0, ())
            else:
                # Second host responds
                return (None, 0, 0, var_binds)

        patches = _patch_snmp(get_cmd_side_effect=alternating_get_cmd)

        with patches["transport"], patches["get_cmd"], patches["engine"]:
            result = await discover_snmp(
                targets=["192.168.1.10", "192.168.1.11"],
                community="public",
                timeout=2.0,
            )

        assert len(result) == 1
        assert result[0].ip_address == "192.168.1.11"

    async def test_returns_empty_for_no_targets(self) -> None:
        """Empty target list returns empty results."""
        result = await discover_snmp(targets=[], community="public", timeout=2.0)
        assert result == []

    async def test_community_string_passed_to_snmp(self) -> None:
        """The community string is forwarded to CommunityData."""
        var_binds = _make_var_binds("Printer", "TestPrinter")
        patches = _patch_snmp(var_binds=var_binds)

        with (
            patches["transport"],
            patches["get_cmd"] as mock_get_cmd,
            patches["engine"],
            patch("printer_map.snmp_discovery.CommunityData") as mock_cd,
        ):
            await discover_snmp(
                targets=["192.168.1.10"],
                community="private_community",
                timeout=2.0,
            )

        mock_cd.assert_called_with("private_community")

    async def test_protocol_is_snmp(self) -> None:
        """All returned records have protocol set to SNMP."""
        var_binds = _make_var_binds("Printer", "TestPrinter")
        patches = _patch_snmp(var_binds=var_binds)

        with patches["transport"], patches["get_cmd"], patches["engine"]:
            result = await discover_snmp(
                targets=["192.168.1.10"],
                community="public",
                timeout=2.0,
            )

        assert len(result) == 1
        assert "SNMP" in result[0].protocols

    async def test_timeout_passed_to_transport(self) -> None:
        """The timeout value is forwarded to UdpTransportTarget.create."""
        var_binds = _make_var_binds("Printer", "TestPrinter")
        patches = _patch_snmp(var_binds=var_binds)

        with (
            patches["transport"] as mock_transport_cls,
            patches["get_cmd"],
            patches["engine"],
        ):
            await discover_snmp(
                targets=["192.168.1.10"],
                community="public",
                timeout=3.5,
            )

        mock_transport_cls.create.assert_called_once_with(
            ("192.168.1.10", 161),
            timeout=3.5,
            retries=0,
        )
