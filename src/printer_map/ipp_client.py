"""IPP client for querying printer capabilities via Get-Printer-Attributes."""

from __future__ import annotations

import logging
import struct
from typing import Any

import aiohttp

from printer_map.models import PrinterRecord

logger = logging.getLogger(__name__)

# IPP constants
IPP_VERSION_MAJOR = 2
IPP_VERSION_MINOR = 0
IPP_OP_GET_PRINTER_ATTRIBUTES = 0x000B
IPP_DEFAULT_PORT = 631

# IPP tag values
TAG_OPERATION_ATTRIBUTES = 0x01
TAG_END_OF_ATTRIBUTES = 0x03
TAG_PRINTER_ATTRIBUTES = 0x04

# Value tags
TAG_INTEGER = 0x21
TAG_BOOLEAN = 0x22
TAG_ENUM = 0x23
TAG_KEYWORD = 0x44
TAG_CHARSET = 0x47
TAG_NATURAL_LANGUAGE = 0x48
TAG_MIME_MEDIA_TYPE = 0x49
TAG_NAME_WITHOUT_LANGUAGE = 0x41
TAG_TEXT_WITHOUT_LANGUAGE = 0x41
TAG_URI = 0x45
TAG_RESOLUTION = 0x32


def _build_get_printer_attributes_request(printer_uri: str) -> bytes:
    """Build a minimal IPP Get-Printer-Attributes request payload."""
    buf = bytearray()

    # Version 2.0
    buf.append(IPP_VERSION_MAJOR)
    buf.append(IPP_VERSION_MINOR)

    # Operation: Get-Printer-Attributes
    buf.extend(struct.pack(">H", IPP_OP_GET_PRINTER_ATTRIBUTES))

    # Request ID
    buf.extend(struct.pack(">I", 1))

    # Operation attributes group
    buf.append(TAG_OPERATION_ATTRIBUTES)

    # attributes-charset = utf-8
    charset_name = b"attributes-charset"
    charset_value = b"utf-8"
    buf.append(TAG_CHARSET)
    buf.extend(struct.pack(">H", len(charset_name)))
    buf.extend(charset_name)
    buf.extend(struct.pack(">H", len(charset_value)))
    buf.extend(charset_value)

    # attributes-natural-language = en
    lang_name = b"attributes-natural-language"
    lang_value = b"en"
    buf.append(TAG_NATURAL_LANGUAGE)
    buf.extend(struct.pack(">H", len(lang_name)))
    buf.extend(lang_name)
    buf.extend(struct.pack(">H", len(lang_value)))
    buf.extend(lang_value)

    # printer-uri
    uri_name = b"printer-uri"
    uri_value = printer_uri.encode("utf-8")
    buf.append(TAG_URI)
    buf.extend(struct.pack(">H", len(uri_name)))
    buf.extend(uri_name)
    buf.extend(struct.pack(">H", len(uri_value)))
    buf.extend(uri_value)

    # End of attributes
    buf.append(TAG_END_OF_ATTRIBUTES)

    return bytes(buf)


def _parse_ipp_response(data: bytes) -> dict[str, Any]:
    """Parse an IPP response and extract printer attribute name-value pairs.

    Returns a dict mapping attribute names to their values. Multi-valued
    attributes are collected into lists.
    """
    attrs: dict[str, Any] = {}
    offset = 0

    if len(data) < 8:
        return attrs

    # Skip version (2 bytes), status-code (2 bytes), request-id (4 bytes)
    offset = 8

    current_attr_name: str = ""

    while offset < len(data):
        tag = data[offset]
        offset += 1

        # Delimiter tags (group tags)
        if tag == TAG_END_OF_ATTRIBUTES:
            break
        if tag < 0x10:
            # Group delimiter tag — skip, continue reading attributes
            continue

        # Value tag — read attribute name length
        if offset + 2 > len(data):
            break
        name_length = struct.unpack(">H", data[offset : offset + 2])[0]
        offset += 2

        if offset + name_length > len(data):
            break
        if name_length > 0:
            current_attr_name = data[offset : offset + name_length].decode(
                "utf-8", errors="replace"
            )
        offset += name_length

        # Read value length
        if offset + 2 > len(data):
            break
        value_length = struct.unpack(">H", data[offset : offset + 2])[0]
        offset += 2

        if offset + value_length > len(data):
            break
        raw_value = data[offset : offset + value_length]
        offset += value_length

        # Decode value based on tag type
        value: Any
        if tag == TAG_BOOLEAN:
            value = bool(raw_value[0]) if value_length >= 1 else False
        elif tag == TAG_INTEGER or tag == TAG_ENUM:
            value = struct.unpack(">i", raw_value)[0] if value_length == 4 else 0
        elif tag == TAG_RESOLUTION:
            if value_length == 9:
                cross_feed = struct.unpack(">i", raw_value[0:4])[0]
                feed = struct.unpack(">i", raw_value[4:8])[0]
                units = raw_value[8]
                unit_str = "dpi" if units == 3 else "dpcm"
                value = f"{cross_feed}x{feed}{unit_str}"
            else:
                value = raw_value.hex()
        else:
            # Text, keyword, URI, charset, natural-language, mime-media-type, etc.
            value = raw_value.decode("utf-8", errors="replace")

        # Collect into attrs — multi-valued attributes become lists
        if current_attr_name in attrs:
            existing = attrs[current_attr_name]
            if isinstance(existing, list):
                existing.append(value)
            else:
                attrs[current_attr_name] = [existing, value]
        else:
            attrs[current_attr_name] = value

    return attrs


def _extract_capabilities(attrs: dict[str, Any]) -> dict[str, Any]:
    """Extract printer capabilities from parsed IPP attributes.

    This is the core extraction logic, separated for testability.

    Args:
        attrs: Dictionary of IPP attribute name → value(s).

    Returns:
        Dictionary with keys: supported_formats, resolutions,
        color_supported, duplex_supported.
    """
    # supported_formats from document-format-supported
    raw_formats = attrs.get("document-format-supported", [])
    if isinstance(raw_formats, list):
        supported_formats = [str(f) for f in raw_formats]
    else:
        supported_formats = [str(raw_formats)]

    # resolutions from printer-resolution-supported
    raw_resolutions = attrs.get("printer-resolution-supported", [])
    if isinstance(raw_resolutions, list):
        resolutions = [str(r) for r in raw_resolutions]
    else:
        resolutions = [str(raw_resolutions)]

    # color_supported from color-supported
    raw_color = attrs.get("color-supported")
    if isinstance(raw_color, bool):
        color_supported: bool | str = raw_color
    elif isinstance(raw_color, list) and len(raw_color) > 0:
        color_supported = bool(raw_color[0])
    else:
        color_supported = "unknown"

    # duplex_supported from sides-supported
    raw_sides = attrs.get("sides-supported", [])
    if isinstance(raw_sides, str):
        raw_sides = [raw_sides]
    if isinstance(raw_sides, list) and len(raw_sides) > 0:
        duplex_supported: bool | str = any(
            "two-sided" in str(s) for s in raw_sides
        )
    else:
        duplex_supported = "unknown"

    return {
        "supported_formats": supported_formats,
        "resolutions": resolutions,
        "color_supported": color_supported,
        "duplex_supported": duplex_supported,
    }


async def query_ipp_attributes(record: PrinterRecord) -> PrinterRecord:
    """Send Get-Printer-Attributes and enrich the record with capabilities.

    Args:
        record: An existing PrinterRecord to enrich.

    Returns:
        The same PrinterRecord with capability fields populated.
        On connection failure, capability fields are set to "unknown".
    """
    ip = record.ip_address
    # Determine the IPP port. If the record came from a _pdl-datastream
    # service (port 9100), that's the raw/JetDirect port — not IPP.
    # Fall back to the standard IPP port (631) in that case.
    raw_port = record.raw_metadata.get("port", IPP_DEFAULT_PORT)
    service_type = record.raw_metadata.get("service_type", "")
    if "_pdl-datastream" in service_type and raw_port == 9100:
        port = IPP_DEFAULT_PORT
    else:
        port = raw_port
    printer_uri = f"ipp://{ip}:{port}/ipp/print"

    request_payload = _build_get_printer_attributes_request(printer_uri)

    url = f"http://{ip}:{port}/ipp/print"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                data=request_payload,
                headers={"Content-Type": "application/ipp"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response_data = await response.read()

        attrs = _parse_ipp_response(response_data)
        capabilities = _extract_capabilities(attrs)

        record.supported_formats = capabilities["supported_formats"]
        record.resolutions = capabilities["resolutions"]
        record.color_supported = capabilities["color_supported"]
        record.duplex_supported = capabilities["duplex_supported"]

    except Exception:
        logger.warning(
            "IPP connection failed for %s:%s, marking capabilities as unknown",
            ip,
            port,
            exc_info=logger.isEnabledFor(logging.DEBUG),
        )
        record.supported_formats = []
        record.resolutions = []
        record.color_supported = "unknown"
        record.duplex_supported = "unknown"

    return record
