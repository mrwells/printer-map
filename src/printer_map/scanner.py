"""Scanner orchestration: discovery, enrichment, merge, and deduplication."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import sys
from typing import Any

from printer_map.config import ScanConfig
from printer_map.ipp_client import query_ipp_attributes
from printer_map.mdns_discovery import discover_mdns
from printer_map.models import PrinterRecord
from printer_map.snmp_discovery import discover_snmp

logger = logging.getLogger(__name__)


def expand_targets(targets: list[str]) -> list[str]:
    """Expand CIDR ranges into individual IP addresses.

    Plain IP addresses and hostnames are passed through unchanged.
    CIDR notation (e.g. "192.168.1.0/30") is expanded into host addresses.
    """
    expanded: list[str] = []
    for target in targets:
        try:
            network = ipaddress.ip_network(target, strict=False)
            if network.prefixlen == network.max_prefixlen:
                # Single host address (e.g. /32 for IPv4)
                expanded.append(str(network.network_address))
            else:
                expanded.extend(str(ip) for ip in network.hosts())
        except ValueError:
            # Not a valid IP/CIDR — treat as hostname
            expanded.append(target)
    return expanded


def validate_targets(targets: list[str]) -> list[str]:
    """Validate all target strings.

    Returns a list of error messages. An empty list means all targets are valid.
    """
    errors: list[str] = []
    for target in targets:
        # Try as IP address
        try:
            ipaddress.ip_address(target)
            continue
        except ValueError:
            pass
        # Try as CIDR network
        try:
            ipaddress.ip_network(target, strict=False)
            continue
        except ValueError:
            pass
        # Try as hostname
        try:
            socket.getaddrinfo(target, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            continue
        except (socket.gaierror, OSError):
            pass
        errors.append(f"Invalid target: {target!r}")
    return errors


def merge_records(records: list[PrinterRecord]) -> list[PrinterRecord]:
    """Merge PrinterRecords by IP address.

    Records sharing the same ip_address are combined:
    - protocols: union, preserving order, no duplicates
    - name: prefer non-empty; if both non-empty, prefer mDNS name
    - hostname: prefer non-empty
    - supported_formats, resolutions: union of both lists
    - color_supported, duplex_supported: prefer boolean over "unknown"
    - raw_metadata: shallow merge (later keys overwrite)
    """
    by_ip: dict[str, PrinterRecord] = {}
    for record in records:
        ip = record.ip_address
        if ip not in by_ip:
            by_ip[ip] = PrinterRecord(
                ip_address=ip,
                hostname=record.hostname,
                name=record.name,
                protocols=list(record.protocols),
                supported_formats=list(record.supported_formats),
                resolutions=list(record.resolutions),
                color_supported=record.color_supported,
                duplex_supported=record.duplex_supported,
                raw_metadata=dict(record.raw_metadata),
            )
        else:
            existing = by_ip[ip]
            # Merge protocols (union, no duplicates)
            for proto in record.protocols:
                if proto not in existing.protocols:
                    existing.protocols.append(proto)
            # Name: prefer non-empty; if both non-empty, prefer mDNS name
            if not existing.name and record.name:
                existing.name = record.name
            elif existing.name and record.name and "mDNS" in record.protocols:
                existing.name = record.name
            # Hostname: prefer non-empty
            if not existing.hostname and record.hostname:
                existing.hostname = record.hostname
            # Union of formats and resolutions
            for fmt in record.supported_formats:
                if fmt not in existing.supported_formats:
                    existing.supported_formats.append(fmt)
            for res in record.resolutions:
                if res not in existing.resolutions:
                    existing.resolutions.append(res)
            # Prefer boolean over "unknown"
            if existing.color_supported == "unknown" and isinstance(record.color_supported, bool):
                existing.color_supported = record.color_supported
            if existing.duplex_supported == "unknown" and isinstance(record.duplex_supported, bool):
                existing.duplex_supported = record.duplex_supported
            # Shallow merge raw_metadata
            existing.raw_metadata.update(record.raw_metadata)
    return list(by_ip.values())


async def run_scan(config: ScanConfig) -> list[PrinterRecord]:
    """Orchestrate discovery, enrichment, merge, and deduplication.

    1. Validate and expand targets.
    2. Run mDNS and SNMP discovery concurrently.
    3. Merge records by IP address.
    4. Enrich each merged record via IPP.
    5. Return the final deduplicated list.

    Progress is reported to stderr at each phase transition.
    """
    # Validate targets
    if config.targets:
        errors = validate_targets(config.targets)
        if errors:
            for err in errors:
                print(err, file=sys.stderr)
            raise SystemExit(1)
        snmp_targets = expand_targets(config.targets)
    else:
        snmp_targets = []

    # Phase 1: Discovery
    print("Phase 1: Discovering printers...", file=sys.stderr)

    mdns_coro = _safe_discover_mdns(config.timeout)
    snmp_coro = _safe_discover_snmp(snmp_targets, config.community, config.timeout)

    mdns_results, snmp_results = await asyncio.gather(mdns_coro, snmp_coro)

    print(
        f"  mDNS: {len(mdns_results)} printer(s) found, "
        f"SNMP: {len(snmp_results)} printer(s) found",
        file=sys.stderr,
    )

    # Phase 2: Merge
    print("Phase 2: Merging records...", file=sys.stderr)
    all_records = mdns_results + snmp_results
    merged = merge_records(all_records)
    print(f"  {len(merged)} unique printer(s) after merge", file=sys.stderr)

    # Phase 3: IPP enrichment
    print("Phase 3: Querying IPP capabilities...", file=sys.stderr)
    enriched: list[PrinterRecord] = []
    for record in merged:
        try:
            enriched_record = await query_ipp_attributes(record)
            enriched.append(enriched_record)
        except Exception:
            logger.warning(
                "IPP enrichment failed for %s, keeping record as-is",
                record.ip_address,
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )
            enriched.append(record)
    print(f"  {len(enriched)} printer(s) enriched", file=sys.stderr)

    return enriched


async def _safe_discover_mdns(timeout: float) -> list[PrinterRecord]:
    """Run mDNS discovery, returning empty list on failure."""
    try:
        return await discover_mdns(timeout=timeout)
    except Exception:
        logger.warning("mDNS discovery failed entirely", exc_info=logger.isEnabledFor(logging.DEBUG))
        return []


async def _safe_discover_snmp(
    targets: list[str], community: str, timeout: float
) -> list[PrinterRecord]:
    """Run SNMP discovery, returning empty list on failure."""
    try:
        return await discover_snmp(targets=targets, community=community, timeout=timeout)
    except Exception:
        logger.warning("SNMP discovery failed entirely", exc_info=logger.isEnabledFor(logging.DEBUG))
        return []
