"""
Unit tests for IPP client module.

Tests attribute extraction with mocked IPP responses, connection failure
handling, and specific known printer attribute sets.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

import struct
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from printer_map.ipp_client import (
    IPP_DEFAULT_PORT,
    TAG_BOOLEAN,
    TAG_CHARSET,
    TAG_END_OF_ATTRIBUTES,
    TAG_KEYWORD,
    TAG_MIME_MEDIA_TYPE,
    TAG_NATURAL_LANGUAGE,
    TAG_OPERATION_ATTRIBUTES,
    TAG_PRINTER_ATTRIBUTES,
    TAG_RESOLUTION,
    _build_get_printer_attributes_request,
    _extract_capabilities,
    _parse_ipp_response,
    query_ipp_attributes,
)
from printer_map.models import PrinterRecord


# --- Helpers ---

def _build_ipp_response(attrs: dict[str, list[tuple[int, bytes]]]) -> bytes:
    """Build a minimal IPP response with the given printer attributes.

    Args:
        attrs: Mapping of attribute name to list of (value_tag, raw_value) tuples.
    """
    buf = bytearray()

    # Version 2.0
    buf.append(0x02)
    buf.append(0x00)
    # Status: successful-ok (0x0000)
    buf.extend(struct.pack(">H", 0x0000))
    # Request ID
    buf.extend(struct.pack(">I", 1))

    # Operation attributes group (minimal)
    buf.append(TAG_OPERATION_ATTRIBUTES)
    # charset
    buf.append(TAG_CHARSET)
    name = b"attributes-charset"
    buf.extend(struct.pack(">H", len(name)))
    buf.extend(name)
    val = b"utf-8"
    buf.extend(struct.pack(">H", len(val)))
    buf.extend(val)

    # Printer attributes group
    buf.append(TAG_PRINTER_ATTRIBUTES)

    for attr_name, values in attrs.items():
        name_bytes = attr_name.encode("utf-8")
        for i, (tag, raw_val) in enumerate(values):
            buf.append(tag)
            if i == 0:
                # First value carries the attribute name
                buf.extend(struct.pack(">H", len(name_bytes)))
                buf.extend(name_bytes)
            else:
                # Additional values have zero-length name (multi-value)
                buf.extend(struct.pack(">H", 0))
            buf.extend(struct.pack(">H", len(raw_val)))
            buf.extend(raw_val)

    buf.append(TAG_END_OF_ATTRIBUTES)
    return bytes(buf)


def _keyword_val(s: str) -> tuple[int, bytes]:
    return (TAG_KEYWORD, s.encode("utf-8"))


def _mime_val(s: str) -> tuple[int, bytes]:
    return (TAG_MIME_MEDIA_TYPE, s.encode("utf-8"))


def _bool_val(b: bool) -> tuple[int, bytes]:
    return (TAG_BOOLEAN, bytes([1 if b else 0]))


def _resolution_val(cross: int, feed: int, units: int = 3) -> tuple[int, bytes]:
    return (TAG_RESOLUTION, struct.pack(">iiB", cross, feed, units))


# --- _extract_capabilities ---

class TestExtractCapabilities:
    def test_extracts_all_formats(self) -> None:
        attrs: dict[str, Any] = {
            "document-format-supported": ["application/pdf", "image/jpeg"],
            "printer-resolution-supported": ["600x600dpi"],
            "color-supported": True,
            "sides-supported": ["one-sided"],
        }
        result = _extract_capabilities(attrs)
        assert result["supported_formats"] == ["application/pdf", "image/jpeg"]

    def test_extracts_resolutions(self) -> None:
        attrs: dict[str, Any] = {
            "document-format-supported": ["application/pdf"],
            "printer-resolution-supported": ["300x300dpi", "600x600dpi"],
            "color-supported": False,
            "sides-supported": ["one-sided"],
        }
        result = _extract_capabilities(attrs)
        assert result["resolutions"] == ["300x300dpi", "600x600dpi"]

    def test_color_supported_true(self) -> None:
        attrs: dict[str, Any] = {
            "document-format-supported": [],
            "printer-resolution-supported": [],
            "color-supported": True,
            "sides-supported": [],
        }
        result = _extract_capabilities(attrs)
        assert result["color_supported"] is True

    def test_color_supported_false(self) -> None:
        attrs: dict[str, Any] = {
            "document-format-supported": [],
            "printer-resolution-supported": [],
            "color-supported": False,
            "sides-supported": [],
        }
        result = _extract_capabilities(attrs)
        assert result["color_supported"] is False

    def test_duplex_true_when_two_sided_present(self) -> None:
        attrs: dict[str, Any] = {
            "document-format-supported": [],
            "printer-resolution-supported": [],
            "color-supported": True,
            "sides-supported": ["one-sided", "two-sided-long-edge"],
        }
        result = _extract_capabilities(attrs)
        assert result["duplex_supported"] is True

    def test_duplex_false_when_only_one_sided(self) -> None:
        attrs: dict[str, Any] = {
            "document-format-supported": [],
            "printer-resolution-supported": [],
            "color-supported": True,
            "sides-supported": ["one-sided"],
        }
        result = _extract_capabilities(attrs)
        assert result["duplex_supported"] is False

    def test_color_unknown_when_missing(self) -> None:
        attrs: dict[str, Any] = {
            "document-format-supported": ["application/pdf"],
            "printer-resolution-supported": [],
        }
        result = _extract_capabilities(attrs)
        assert result["color_supported"] == "unknown"

    def test_duplex_unknown_when_missing(self) -> None:
        attrs: dict[str, Any] = {
            "document-format-supported": ["application/pdf"],
            "printer-resolution-supported": [],
        }
        result = _extract_capabilities(attrs)
        assert result["duplex_supported"] == "unknown"

    def test_single_format_not_in_list(self) -> None:
        """A single string value (not a list) is wrapped into a list."""
        attrs: dict[str, Any] = {
            "document-format-supported": "application/pdf",
            "printer-resolution-supported": "600x600dpi",
            "color-supported": True,
            "sides-supported": "one-sided",
        }
        result = _extract_capabilities(attrs)
        assert result["supported_formats"] == ["application/pdf"]
        assert result["resolutions"] == ["600x600dpi"]


# --- _parse_ipp_response ---

class TestParseIppResponse:
    def test_parses_keyword_attributes(self) -> None:
        response = _build_ipp_response({
            "sides-supported": [_keyword_val("one-sided"), _keyword_val("two-sided-long-edge")],
        })
        attrs = _parse_ipp_response(response)
        assert "sides-supported" in attrs
        assert "one-sided" in attrs["sides-supported"]
        assert "two-sided-long-edge" in attrs["sides-supported"]

    def test_parses_boolean_attribute(self) -> None:
        response = _build_ipp_response({
            "color-supported": [_bool_val(True)],
        })
        attrs = _parse_ipp_response(response)
        assert attrs["color-supported"] is True

    def test_parses_mime_type_attributes(self) -> None:
        response = _build_ipp_response({
            "document-format-supported": [
                _mime_val("application/pdf"),
                _mime_val("image/jpeg"),
            ],
        })
        attrs = _parse_ipp_response(response)
        assert isinstance(attrs["document-format-supported"], list)
        assert "application/pdf" in attrs["document-format-supported"]
        assert "image/jpeg" in attrs["document-format-supported"]

    def test_parses_resolution_attribute(self) -> None:
        response = _build_ipp_response({
            "printer-resolution-supported": [_resolution_val(600, 600)],
        })
        attrs = _parse_ipp_response(response)
        assert attrs["printer-resolution-supported"] == "600x600dpi"

    def test_empty_response(self) -> None:
        attrs = _parse_ipp_response(b"")
        assert attrs == {}

    def test_truncated_response(self) -> None:
        attrs = _parse_ipp_response(b"\x02\x00\x00\x00")
        assert attrs == {}


# --- _build_get_printer_attributes_request ---

class TestBuildRequest:
    def test_request_starts_with_version(self) -> None:
        req = _build_get_printer_attributes_request("ipp://192.168.1.1:631/ipp/print")
        assert req[0] == 0x02  # major
        assert req[1] == 0x00  # minor

    def test_request_contains_operation_code(self) -> None:
        req = _build_get_printer_attributes_request("ipp://192.168.1.1:631/ipp/print")
        op_code = struct.unpack(">H", req[2:4])[0]
        assert op_code == 0x000B

    def test_request_contains_printer_uri(self) -> None:
        uri = "ipp://192.168.1.1:631/ipp/print"
        req = _build_get_printer_attributes_request(uri)
        assert uri.encode("utf-8") in req


# --- query_ipp_attributes ---

class TestQueryIppAttributes:
    async def test_enriches_record_on_success(self) -> None:
        """Successful IPP query populates capability fields."""
        ipp_response = _build_ipp_response({
            "document-format-supported": [
                _mime_val("application/pdf"),
                _mime_val("image/jpeg"),
            ],
            "printer-resolution-supported": [_resolution_val(600, 600)],
            "color-supported": [_bool_val(True)],
            "sides-supported": [
                _keyword_val("one-sided"),
                _keyword_val("two-sided-long-edge"),
            ],
        })

        mock_response = AsyncMock()
        mock_response.read = AsyncMock(return_value=ipp_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        record = PrinterRecord(
            ip_address="192.168.1.100",
            hostname="printer.local.",
            name="Office Printer",
            protocols=["mDNS"],
            raw_metadata={"port": 631},
        )

        with patch("printer_map.ipp_client.aiohttp.ClientSession", return_value=mock_session):
            result = await query_ipp_attributes(record)

        assert "application/pdf" in result.supported_formats
        assert "image/jpeg" in result.supported_formats
        assert "600x600dpi" in result.resolutions
        assert result.color_supported is True
        assert result.duplex_supported is True

    async def test_marks_unknown_on_connection_failure(self) -> None:
        """Connection failure sets capability fields to 'unknown'."""
        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=Exception("Connection refused"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        record = PrinterRecord(
            ip_address="192.168.1.200",
            hostname="",
            name="Unreachable Printer",
            protocols=["SNMP"],
        )

        with patch("printer_map.ipp_client.aiohttp.ClientSession", return_value=mock_session):
            result = await query_ipp_attributes(record)

        assert result.supported_formats == []
        assert result.resolutions == []
        assert result.color_supported == "unknown"
        assert result.duplex_supported == "unknown"

    async def test_uses_port_from_raw_metadata(self) -> None:
        """Port is read from raw_metadata if available."""
        ipp_response = _build_ipp_response({
            "document-format-supported": [_mime_val("application/pdf")],
            "color-supported": [_bool_val(False)],
            "sides-supported": [_keyword_val("one-sided")],
        })

        mock_response = AsyncMock()
        mock_response.read = AsyncMock(return_value=ipp_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        record = PrinterRecord(
            ip_address="10.0.0.5",
            hostname="",
            name="Custom Port Printer",
            protocols=["mDNS"],
            raw_metadata={"port": 9100},
        )

        with patch("printer_map.ipp_client.aiohttp.ClientSession", return_value=mock_session) as _:
            result = await query_ipp_attributes(record)

        # Verify the URL used the custom port
        call_args = mock_session.post.call_args
        assert "10.0.0.5:9100" in call_args[0][0]

    async def test_defaults_to_port_631(self) -> None:
        """When no port in raw_metadata, defaults to 631."""
        ipp_response = _build_ipp_response({
            "document-format-supported": [_mime_val("application/pdf")],
        })

        mock_response = AsyncMock()
        mock_response.read = AsyncMock(return_value=ipp_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        record = PrinterRecord(
            ip_address="10.0.0.5",
            hostname="",
            name="Default Port Printer",
            protocols=["mDNS"],
        )

        with patch("printer_map.ipp_client.aiohttp.ClientSession", return_value=mock_session):
            await query_ipp_attributes(record)

        call_args = mock_session.post.call_args
        assert "10.0.0.5:631" in call_args[0][0]

    async def test_known_hp_laserjet_attributes(self) -> None:
        """Test with a realistic HP LaserJet attribute set."""
        ipp_response = _build_ipp_response({
            "document-format-supported": [
                _mime_val("application/pdf"),
                _mime_val("application/postscript"),
                _mime_val("application/vnd.hp-pcl"),
                _mime_val("image/jpeg"),
            ],
            "printer-resolution-supported": [
                _resolution_val(300, 300),
                _resolution_val(600, 600),
                _resolution_val(1200, 1200),
            ],
            "color-supported": [_bool_val(True)],
            "sides-supported": [
                _keyword_val("one-sided"),
                _keyword_val("two-sided-long-edge"),
                _keyword_val("two-sided-short-edge"),
            ],
        })

        mock_response = AsyncMock()
        mock_response.read = AsyncMock(return_value=ipp_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        record = PrinterRecord(
            ip_address="192.168.1.50",
            hostname="hp-laserjet.local.",
            name="HP LaserJet Pro",
            protocols=["mDNS"],
            raw_metadata={"port": 631},
        )

        with patch("printer_map.ipp_client.aiohttp.ClientSession", return_value=mock_session):
            result = await query_ipp_attributes(record)

        assert len(result.supported_formats) == 4
        assert "application/pdf" in result.supported_formats
        assert "application/postscript" in result.supported_formats
        assert len(result.resolutions) == 3
        assert "600x600dpi" in result.resolutions
        assert result.color_supported is True
        assert result.duplex_supported is True
