# Feature: printer-scanner-cli, Property 6: Merge produces unique IPs with combined protocols
# Feature: printer-scanner-cli, Property 7: CIDR expansion correctness
# Feature: printer-scanner-cli, Property 10: Scanner resilience to protocol failures
"""
Property 6: Merge produces unique IPs with combined protocols
Property 7: CIDR expansion correctness
Property 10: Scanner resilience to protocol failures

Validates: Requirements 4.3, 6.2, 6.3, 9.1
"""

from __future__ import annotations

import ipaddress
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from printer_map.models import PrinterRecord
from printer_map.scanner import expand_targets, merge_records, run_scan
from printer_map.config import ScanConfig


# --- Shared strategies ---

ipv4_addresses = st.tuples(
    st.integers(min_value=1, max_value=254),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=1, max_value=254),
).map(lambda t: f"{t[0]}.{t[1]}.{t[2]}.{t[3]}")

protocols = st.sampled_from(["mDNS", "SNMP", "IPP"])

printer_records = st.builds(
    PrinterRecord,
    ip_address=ipv4_addresses,
    hostname=st.text(max_size=30),
    name=st.text(max_size=30),
    protocols=st.lists(protocols, min_size=1, max_size=3),
    supported_formats=st.lists(st.text(max_size=20), max_size=3),
    resolutions=st.lists(st.text(max_size=20), max_size=3),
    color_supported=st.one_of(st.booleans(), st.just("unknown")),
    duplex_supported=st.one_of(st.booleans(), st.just("unknown")),
    raw_metadata=st.just({}),
)


# --- Property 6: Merge produces unique IPs with combined protocols ---

@settings(max_examples=100)
@given(records=st.lists(printer_records, min_size=0, max_size=20))
def test_merge_produces_unique_ips_with_combined_protocols(
    records: list[PrinterRecord],
) -> None:
    """
    **Validates: Requirements 6.2, 6.3**

    For any list of PrinterRecord objects (possibly containing duplicates by IP
    address), merging them should produce a list where each IP address appears
    exactly once, and for each IP the merged record's protocols list is the
    union of all protocols from the input records with that IP.
    """
    merged = merge_records(records)

    # All IPs are unique
    merged_ips = [r.ip_address for r in merged]
    assert len(merged_ips) == len(set(merged_ips))

    # For each IP, protocols are the union of input protocols
    for merged_record in merged:
        ip = merged_record.ip_address
        expected_protocols: set[str] = set()
        for r in records:
            if r.ip_address == ip:
                expected_protocols.update(r.protocols)
        assert set(merged_record.protocols) == expected_protocols


# --- Property 7: CIDR expansion correctness ---

# Generate valid CIDR ranges with /28-/30 prefixes to keep tests fast
cidr_ranges = st.tuples(
    st.integers(min_value=1, max_value=254),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=28, max_value=30),
).map(lambda t: f"{t[0]}.{t[1]}.{t[2]}.{t[3]}/{t[4]}")


@settings(max_examples=100)
@given(cidr=cidr_ranges)
def test_cidr_expansion_correctness(cidr: str) -> None:
    """
    **Validates: Requirements 4.3**

    For any valid CIDR range string, expanding it into individual IP addresses
    should produce exactly the set of host addresses defined by
    ipaddress.ip_network(cidr, strict=False).hosts().
    """
    expanded = expand_targets([cidr])
    expected = [str(ip) for ip in ipaddress.ip_network(cidr, strict=False).hosts()]
    assert expanded == expected


# --- Property 10: Scanner resilience to protocol failures ---

@settings(max_examples=100)
@given(
    mdns_fails=st.booleans(),
    snmp_fails=st.booleans(),
    mdns_records=st.lists(printer_records, min_size=0, max_size=5),
    snmp_records=st.lists(printer_records, min_size=0, max_size=5),
)
async def test_scanner_resilience_to_protocol_failures(
    mdns_fails: bool,
    snmp_fails: bool,
    mdns_records: list[PrinterRecord],
    snmp_records: list[PrinterRecord],
) -> None:
    """
    **Validates: Requirements 9.1**

    For any combination of protocol discovery failures (mDNS fails, SNMP fails,
    or both fail), the scanner should still return results from the non-failing
    protocols without raising an exception. If all protocols fail, it should
    return an empty list.
    """
    config = ScanConfig(targets=[], timeout=1.0)

    async def mock_mdns(timeout: float) -> list[PrinterRecord]:
        if mdns_fails:
            raise ConnectionError("mDNS failed")
        return mdns_records

    async def mock_snmp(
        targets: list[str], community: str, timeout: float
    ) -> list[PrinterRecord]:
        if snmp_fails:
            raise ConnectionError("SNMP failed")
        return snmp_records

    mock_ipp = AsyncMock(side_effect=lambda r: r)

    with (
        patch("printer_map.scanner.discover_mdns", side_effect=mock_mdns),
        patch("printer_map.scanner.discover_snmp", side_effect=mock_snmp),
        patch("printer_map.scanner.query_ipp_attributes", mock_ipp),
    ):
        results = await run_scan(config)

    # Should never raise — just return what it can
    expected_count = 0
    if not mdns_fails:
        expected_count += len(mdns_records)
    if not snmp_fails:
        expected_count += len(snmp_records)

    # After merge, count may be less due to IP dedup, but should not exceed
    assert len(results) <= expected_count

    if mdns_fails and snmp_fails:
        assert results == []
