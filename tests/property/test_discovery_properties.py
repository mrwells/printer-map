# Feature: printer-scanner-cli, Property 12: mDNS service resolution extracts all fields
# Feature: printer-scanner-cli, Property 4: Discovery sets correct protocol field
"""
Property 12: mDNS service resolution extracts all fields
Property 4: Discovery sets correct protocol field

Validates: Requirements 1.2, 1.3, 2.4
"""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from printer_map.mdns_discovery import _service_info_to_record


# --- Hypothesis strategies for ServiceInfo-like objects ---

# Valid IPv4 addresses
ipv4_addresses = st.tuples(
    st.integers(min_value=1, max_value=254),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=1, max_value=254),
).map(lambda t: f"{t[0]}.{t[1]}.{t[2]}.{t[3]}")

# Hostnames
hostnames = st.from_regex(r"[a-z][a-z0-9]{0,9}\.local\.", fullmatch=True)

# Service names
service_names = st.from_regex(r"[A-Za-z][A-Za-z0-9 ]{0,19}", fullmatch=True)

# Ports
ports = st.integers(min_value=1, max_value=65535)

# TXT record key-value pairs (bytes)
_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=20,
)
txt_properties = st.dictionaries(
    keys=_safe_text.map(lambda s: s.encode("utf-8")),
    values=_safe_text.map(lambda s: s.encode("utf-8")),
    max_size=5,
)

# Service types
service_types = st.sampled_from([
    "_ipp._tcp.local.",
    "_ipps._tcp.local.",
    "_pdl-datastream._tcp.local.",
])


class FakeServiceInfo:
    """Minimal mock of AsyncServiceInfo for property testing."""

    def __init__(
        self,
        ip: str,
        hostname: str,
        name: str,
        port: int,
        properties: dict[bytes, bytes],
        service_type: str,
    ) -> None:
        self._ip = ip
        self.server = hostname
        self.name = name
        self.port = port
        self.properties = properties
        self.type = service_type

    def parsed_scoped_addresses(self) -> list[str]:
        return [self._ip]


@settings(max_examples=100)
@given(
    ip=ipv4_addresses,
    hostname=hostnames,
    name=service_names,
    port=ports,
    properties=txt_properties,
    service_type=service_types,
)
def test_mdns_service_resolution_extracts_all_fields(
    ip: str,
    hostname: str,
    name: str,
    port: int,
    properties: dict[bytes, bytes],
    service_type: str,
) -> None:
    """
    **Validates: Requirements 1.2**

    For any mDNS ServiceInfo object containing a hostname, IP address, port,
    and TXT record properties, resolving it into a PrinterRecord should produce
    a record where hostname, ip_address, and raw_metadata all contain the
    corresponding values from the ServiceInfo.
    """
    fake_info = FakeServiceInfo(
        ip=ip,
        hostname=hostname,
        name=name,
        port=port,
        properties=properties,
        service_type=service_type,
    )

    record = _service_info_to_record(fake_info)

    assert record is not None
    assert record.ip_address == ip
    assert record.hostname == hostname
    assert record.name == name
    assert record.raw_metadata["port"] == port
    assert record.raw_metadata["service_type"] == service_type

    # All TXT record keys should appear in raw_metadata["txt"]
    txt = record.raw_metadata["txt"]
    for key_bytes, val_bytes in properties.items():
        key = key_bytes.decode("utf-8", errors="replace")
        val = val_bytes.decode("utf-8", errors="replace")
        assert key in txt
        assert txt[key] == val


@settings(max_examples=100)
@given(
    ip=ipv4_addresses,
    hostname=hostnames,
    name=service_names,
    port=ports,
    service_type=service_types,
)
def test_discovery_sets_correct_protocol_field(
    ip: str,
    hostname: str,
    name: str,
    port: int,
    service_type: str,
) -> None:
    """
    **Validates: Requirements 1.3, 2.4**

    For any printer discovered by mDNS, the resulting PrinterRecord should
    contain "mDNS" in its protocols list.
    """
    fake_info = FakeServiceInfo(
        ip=ip,
        hostname=hostname,
        name=name,
        port=port,
        properties={},
        service_type=service_type,
    )

    record = _service_info_to_record(fake_info)

    assert record is not None
    assert "mDNS" in record.protocols


# Feature: printer-scanner-cli, Property 5: IPP attribute extraction completeness
"""
Property 5: IPP attribute extraction completeness

Validates: Requirements 3.2, 3.3, 3.4, 3.5
"""

from printer_map.ipp_client import _extract_capabilities

# --- Hypothesis strategies for IPP attributes ---

# MIME types for document-format-supported
_mime_types = st.sampled_from([
    "application/pdf",
    "application/postscript",
    "image/jpeg",
    "image/png",
    "application/octet-stream",
    "text/plain",
    "application/vnd.hp-pcl",
    "image/pwg-raster",
])

# Resolution strings for printer-resolution-supported
_resolutions = st.sampled_from([
    "300x300dpi",
    "600x600dpi",
    "1200x1200dpi",
    "600x1200dpi",
    "300x600dpi",
    "2400x600dpi",
])

# Sides values for sides-supported
_sides_values = st.sampled_from([
    "one-sided",
    "two-sided-long-edge",
    "two-sided-short-edge",
])


@settings(max_examples=100)
@given(
    formats=st.lists(_mime_types, min_size=1, max_size=8),
    resolutions=st.lists(_resolutions, min_size=1, max_size=5),
    color=st.booleans(),
    sides=st.lists(_sides_values, min_size=1, max_size=3),
)
def test_ipp_attribute_extraction_completeness(
    formats: list[str],
    resolutions: list[str],
    color: bool,
    sides: list[str],
) -> None:
    """
    **Validates: Requirements 3.2, 3.3, 3.4, 3.5**

    For any IPP attribute dictionary containing document-format-supported,
    printer-resolution-supported, color-supported, and sides-supported,
    the extracted capabilities should contain all format values in
    supported_formats, all resolution values in resolutions, the correct
    boolean for color_supported, and duplex_supported is True iff any
    "two-sided" value is present in sides-supported.
    """
    attrs: dict[str, Any] = {
        "document-format-supported": formats,
        "printer-resolution-supported": resolutions,
        "color-supported": color,
        "sides-supported": sides,
    }

    result = _extract_capabilities(attrs)

    # All format values appear in supported_formats
    for fmt in formats:
        assert fmt in result["supported_formats"], (
            f"Format {fmt!r} missing from supported_formats"
        )

    # All resolution values appear in resolutions
    for res in resolutions:
        assert res in result["resolutions"], (
            f"Resolution {res!r} missing from resolutions"
        )

    # Correct boolean for color_supported
    assert result["color_supported"] is color, (
        f"Expected color_supported={color}, got {result['color_supported']}"
    )

    # duplex_supported is True iff any "two-sided" value present
    has_two_sided = any("two-sided" in s for s in sides)
    assert result["duplex_supported"] is has_two_sided, (
        f"Expected duplex_supported={has_two_sided}, got {result['duplex_supported']}"
    )
