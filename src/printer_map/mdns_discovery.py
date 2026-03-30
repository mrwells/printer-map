"""mDNS printer discovery using zeroconf."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from printer_map.models import PrinterRecord

logger = logging.getLogger(__name__)

MDNS_SERVICE_TYPES = [
    "_ipp._tcp.local.",
    "_ipps._tcp.local.",
    "_pdl-datastream._tcp.local.",
]


def _parse_txt_record(info: AsyncServiceInfo) -> dict[str, str]:
    """Extract TXT record properties as a string-keyed dict."""
    result: dict[str, str] = {}
    if info.properties:
        for key_bytes, val_bytes in info.properties.items():
            key = key_bytes.decode("utf-8", errors="replace") if isinstance(key_bytes, bytes) else str(key_bytes)
            if isinstance(val_bytes, bytes):
                val = val_bytes.decode("utf-8", errors="replace")
            elif val_bytes is None:
                val = ""
            else:
                val = str(val_bytes)
            result[key] = val
    return result


def _service_info_to_record(info: AsyncServiceInfo) -> PrinterRecord | None:
    """Convert a resolved AsyncServiceInfo into a PrinterRecord."""
    addresses = info.parsed_scoped_addresses()
    if not addresses:
        return None

    ip_address = addresses[0]
    hostname = info.server or ""
    port = info.port or 0
    name = info.name or ""
    # Strip the service type suffix from the mDNS instance name.
    # e.g. "HP Printer._ipp._tcp.local." → "HP Printer"
    if name and info.type and name.endswith(f".{info.type}"):
        name = name[: -(len(info.type) + 1)]
    txt_data = _parse_txt_record(info)

    raw_metadata: dict[str, Any] = {
        "port": port,
        "service_type": info.type,
        "txt": txt_data,
    }

    return PrinterRecord(
        ip_address=ip_address,
        hostname=hostname,
        name=name,
        protocols=["mDNS"],
        raw_metadata=raw_metadata,
    )


async def discover_mdns(timeout: float = 5.0) -> list[PrinterRecord]:
    """Browse mDNS service types and resolve to PrinterRecords.

    Args:
        timeout: How long to browse for services, in seconds.

    Returns:
        List of discovered PrinterRecord objects with protocol set to "mDNS".
        Returns an empty list on network errors.
    """
    records: list[PrinterRecord] = []
    found_services: list[tuple[str, str]] = []

    def on_service_state_change(
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change is ServiceStateChange.Added:
            found_services.append((service_type, name))

    try:
        aiozc = AsyncZeroconf()
        browser = AsyncServiceBrowser(
            aiozc.zeroconf,
            MDNS_SERVICE_TYPES,
            handlers=[on_service_state_change],
        )

        await asyncio.sleep(timeout)

        # Resolve each discovered service
        for service_type, name in found_services:
            try:
                info = AsyncServiceInfo(service_type, name)
                if await info.async_request(aiozc.zeroconf, timeout=3000):
                    record = _service_info_to_record(info)
                    if record is not None:
                        records.append(record)
            except Exception:
                logger.warning("Failed to resolve mDNS service %s", name, exc_info=logger.isEnabledFor(logging.DEBUG))

        await browser.async_cancel()
        await aiozc.async_close()

    except Exception:
        logger.warning("mDNS discovery failed due to network error", exc_info=logger.isEnabledFor(logging.DEBUG))
        return []

    return records
