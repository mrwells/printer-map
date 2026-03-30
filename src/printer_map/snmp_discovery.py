"""SNMP printer discovery using pysnmp."""

from __future__ import annotations

import logging
from typing import Any

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)

from printer_map.models import PrinterRecord

logger = logging.getLogger(__name__)

# OIDs for printer identification
OID_HR_DEVICE_DESCR = "1.3.6.1.2.1.25.3.2.1.3.1"
OID_PRT_GENERAL_PRINTER_NAME = "1.3.6.1.2.1.43.5.1.1.16.1"

SNMP_PORT = 161


async def _query_host(
    engine: SnmpEngine,
    target: str,
    community: str,
    timeout: float,
) -> PrinterRecord | None:
    """Send SNMP GET requests to a single host and return a PrinterRecord if it responds.

    Args:
        engine: Shared SNMP engine instance.
        target: IP address to query.
        community: SNMP community string.
        timeout: Timeout in seconds for the SNMP request.

    Returns:
        A PrinterRecord if the host responds, or None if it doesn't.
    """
    try:
        transport = await UdpTransportTarget.create(
            (target, SNMP_PORT),
            timeout=timeout,
            retries=0,
        )
    except Exception:
        logger.warning("Failed to create SNMP transport for %s", target, exc_info=True)
        return None

    try:
        error_indication, error_status, _error_index, var_binds = await get_cmd(
            engine,
            CommunityData(community),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(OID_HR_DEVICE_DESCR)),
            ObjectType(ObjectIdentity(OID_PRT_GENERAL_PRINTER_NAME)),
        )
    except Exception:
        logger.warning("SNMP query failed for %s", target, exc_info=True)
        return None

    if error_indication:
        logger.debug("SNMP timeout/error for %s: %s", target, error_indication)
        return None

    if error_status:
        logger.debug("SNMP error status for %s: %s", target, error_status)
        return None

    # Extract values from var_binds
    raw_metadata: dict[str, Any] = {}
    device_descr = ""
    printer_name = ""

    for oid, val in var_binds:
        oid_str = str(oid)
        val_str = str(val) if val else ""
        raw_metadata[oid_str] = val_str

        if OID_HR_DEVICE_DESCR in oid_str:
            device_descr = val_str
        elif OID_PRT_GENERAL_PRINTER_NAME in oid_str:
            printer_name = val_str

    name = printer_name or device_descr or ""

    return PrinterRecord(
        ip_address=target,
        hostname="",
        name=name,
        protocols=["SNMP"],
        raw_metadata=raw_metadata,
    )


async def discover_snmp(
    targets: list[str],
    community: str = "public",
    timeout: float = 5.0,
) -> list[PrinterRecord]:
    """Query targets via SNMP GET for printer OIDs.

    Sends SNMP GET requests for hrDeviceDescr and prtGeneralPrinterName
    to each target IP. Non-responding hosts are skipped.

    Args:
        targets: List of IP addresses to query.
        community: SNMP community string (default: "public").
        timeout: Timeout in seconds per host (default: 5.0).

    Returns:
        List of PrinterRecord objects with protocol set to "SNMP".
    """
    records: list[PrinterRecord] = []
    engine = SnmpEngine()

    for target in targets:
        logger.debug("Querying SNMP on %s with community '%s'", target, community)
        record = await _query_host(engine, target, community, timeout)
        if record is not None:
            records.append(record)
            logger.info("SNMP: found printer at %s", target)
        else:
            logger.debug("SNMP: no response from %s, skipping", target)

    return records
