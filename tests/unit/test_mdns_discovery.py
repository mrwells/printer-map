"""
Unit tests for mDNS discovery module.

Tests service resolution with mocked zeroconf, network error handling,
and timeout behavior.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from printer_map.mdns_discovery import (
    MDNS_SERVICE_TYPES,
    _parse_txt_record,
    _service_info_to_record,
    discover_mdns,
)
from printer_map.models import PrinterRecord


# --- Helpers ---

def _make_fake_service_info(
    ip: str = "192.168.1.100",
    hostname: str = "printer.local.",
    name: str = "Office Printer._ipp._tcp.local.",
    port: int = 631,
    service_type: str = "_ipp._tcp.local.",
    properties: dict[bytes, bytes] | None = None,
) -> MagicMock:
    """Create a mock AsyncServiceInfo."""
    info = MagicMock()
    info.parsed_scoped_addresses.return_value = [ip]
    info.server = hostname
    info.name = name
    info.port = port
    info.type = service_type
    info.properties = properties or {b"rp": b"ipp/print", b"ty": b"LaserJet"}
    info.async_request = AsyncMock(return_value=True)
    return info


# --- _parse_txt_record ---

class TestParseTxtRecord:
    def test_parses_bytes_keys_and_values(self) -> None:
        info = MagicMock()
        info.properties = {b"rp": b"ipp/print", b"ty": b"HP LaserJet"}
        result = _parse_txt_record(info)
        assert result == {"rp": "ipp/print", "ty": "HP LaserJet"}

    def test_empty_properties(self) -> None:
        info = MagicMock()
        info.properties = {}
        result = _parse_txt_record(info)
        assert result == {}

    def test_none_properties(self) -> None:
        info = MagicMock()
        info.properties = None
        result = _parse_txt_record(info)
        assert result == {}

    def test_none_value_becomes_empty_string(self) -> None:
        info = MagicMock()
        info.properties = {b"key": None}
        result = _parse_txt_record(info)
        assert result == {"key": ""}


# --- _service_info_to_record ---

class TestServiceInfoToRecord:
    def test_converts_to_printer_record(self) -> None:
        info = _make_fake_service_info()
        record = _service_info_to_record(info)
        assert record is not None
        assert record.ip_address == "192.168.1.100"
        assert record.hostname == "printer.local."
        assert record.name == "Office Printer"
        assert record.protocols == ["mDNS"]
        assert record.raw_metadata["port"] == 631
        assert record.raw_metadata["service_type"] == "_ipp._tcp.local."
        assert record.raw_metadata["txt"]["rp"] == "ipp/print"

    def test_returns_none_when_no_addresses(self) -> None:
        info = _make_fake_service_info()
        info.parsed_scoped_addresses.return_value = []
        record = _service_info_to_record(info)
        assert record is None

    def test_protocol_is_mdns(self) -> None:
        info = _make_fake_service_info()
        record = _service_info_to_record(info)
        assert record is not None
        assert "mDNS" in record.protocols


# --- discover_mdns ---

class TestDiscoverMdns:
    async def test_returns_empty_list_on_network_error(self) -> None:
        """If zeroconf raises an exception, discover_mdns returns []."""
        with patch(
            "printer_map.mdns_discovery.AsyncZeroconf",
            side_effect=OSError("Network unreachable"),
        ):
            result = await discover_mdns(timeout=0.1)
        assert result == []

    async def test_returns_printer_records(self) -> None:
        """Discovered services are resolved and returned as PrinterRecords."""
        mock_aiozc = MagicMock()
        mock_aiozc.zeroconf = MagicMock()
        mock_aiozc.async_close = AsyncMock()

        fake_info = _make_fake_service_info()

        # Capture the handler so we can simulate service discovery
        captured_handlers = []

        def fake_browser_init(zeroconf, service_types, handlers):
            captured_handlers.extend(handlers)
            # Simulate a service being found immediately
            for handler in handlers:
                from zeroconf import ServiceStateChange
                handler(
                    zeroconf,
                    "_ipp._tcp.local.",
                    "Office Printer._ipp._tcp.local.",
                    ServiceStateChange.Added,
                )
            mock_browser = MagicMock()
            mock_browser.async_cancel = AsyncMock()
            return mock_browser

        with (
            patch("printer_map.mdns_discovery.AsyncZeroconf", return_value=mock_aiozc),
            patch("printer_map.mdns_discovery.AsyncServiceBrowser", side_effect=fake_browser_init),
            patch("printer_map.mdns_discovery.AsyncServiceInfo", return_value=fake_info),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await discover_mdns(timeout=0.1)

        assert len(result) == 1
        assert result[0].ip_address == "192.168.1.100"
        assert result[0].protocols == ["mDNS"]

    async def test_timeout_controls_browse_duration(self) -> None:
        """The timeout parameter is passed to asyncio.sleep for browse duration."""
        mock_aiozc = MagicMock()
        mock_aiozc.zeroconf = MagicMock()
        mock_aiozc.async_close = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.async_cancel = AsyncMock()

        sleep_mock = AsyncMock()

        with (
            patch("printer_map.mdns_discovery.AsyncZeroconf", return_value=mock_aiozc),
            patch("printer_map.mdns_discovery.AsyncServiceBrowser", return_value=mock_browser),
            patch("asyncio.sleep", sleep_mock),
        ):
            await discover_mdns(timeout=7.5)

        sleep_mock.assert_awaited_once_with(7.5)

    async def test_skips_unresolvable_services(self) -> None:
        """Services that fail to resolve are skipped."""
        mock_aiozc = MagicMock()
        mock_aiozc.zeroconf = MagicMock()
        mock_aiozc.async_close = AsyncMock()

        # Info that fails to resolve
        bad_info = MagicMock()
        bad_info.async_request = AsyncMock(return_value=False)

        def fake_browser_init(zeroconf, service_types, handlers):
            from zeroconf import ServiceStateChange
            for handler in handlers:
                handler(zeroconf, "_ipp._tcp.local.", "Bad._ipp._tcp.local.", ServiceStateChange.Added)
            mock_browser = MagicMock()
            mock_browser.async_cancel = AsyncMock()
            return mock_browser

        with (
            patch("printer_map.mdns_discovery.AsyncZeroconf", return_value=mock_aiozc),
            patch("printer_map.mdns_discovery.AsyncServiceBrowser", side_effect=fake_browser_init),
            patch("printer_map.mdns_discovery.AsyncServiceInfo", return_value=bad_info),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await discover_mdns(timeout=0.1)

        assert result == []

    async def test_handles_resolution_exception(self) -> None:
        """If resolving a service raises, it is logged and skipped."""
        mock_aiozc = MagicMock()
        mock_aiozc.zeroconf = MagicMock()
        mock_aiozc.async_close = AsyncMock()

        bad_info = MagicMock()
        bad_info.async_request = AsyncMock(side_effect=Exception("resolve failed"))

        def fake_browser_init(zeroconf, service_types, handlers):
            from zeroconf import ServiceStateChange
            for handler in handlers:
                handler(zeroconf, "_ipp._tcp.local.", "Err._ipp._tcp.local.", ServiceStateChange.Added)
            mock_browser = MagicMock()
            mock_browser.async_cancel = AsyncMock()
            return mock_browser

        with (
            patch("printer_map.mdns_discovery.AsyncZeroconf", return_value=mock_aiozc),
            patch("printer_map.mdns_discovery.AsyncServiceBrowser", side_effect=fake_browser_init),
            patch("printer_map.mdns_discovery.AsyncServiceInfo", return_value=bad_info),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await discover_mdns(timeout=0.1)

        assert result == []
