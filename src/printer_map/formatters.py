"""Output formatters for printer scan results."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from printer_map.models import PrinterRecord

COLUMNS = ["IP", "Name", "Protocols", "Formats", "Resolution", "Color", "Duplex"]


def _record_row(record: PrinterRecord) -> list[str]:
    """Convert a PrinterRecord into a list of display strings for one row."""
    return [
        record.ip_address,
        record.name,
        ", ".join(record.protocols),
        ", ".join(record.supported_formats),
        ", ".join(record.resolutions),
        str(record.color_supported),
        str(record.duplex_supported),
    ]


def format_table(records: list[PrinterRecord]) -> str:
    """Render records as a readable card-style table.

    Each printer is displayed as a block with labelled fields,
    which avoids the readability problems of very wide column-aligned rows.
    """
    if not records:
        return ""

    blocks: list[str] = []
    for i, record in enumerate(records, 1):
        lines = [
            f"Printer {i}: {record.name or '(unnamed)'}",
            f"  IP:          {record.ip_address}",
            f"  Hostname:    {record.hostname or '—'}",
            f"  Protocols:   {', '.join(record.protocols) or '—'}",
            f"  Formats:     {', '.join(record.supported_formats) or '—'}",
            f"  Resolution:  {', '.join(record.resolutions) or '—'}",
            f"  Color:       {record.color_supported}",
            f"  Duplex:      {record.duplex_supported}",
        ]
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def format_json(records: list[PrinterRecord]) -> str:
    """Render records as a JSON array with indent=2."""
    return json.dumps([record.to_dict() for record in records], indent=2)


def format_csv(records: list[PrinterRecord]) -> str:
    """Render records as RFC 4180 compliant CSV with a header row."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    for record in records:
        writer.writerow(_record_row(record))
    return output.getvalue()


def format_output(records: list[PrinterRecord], fmt: str) -> str:
    """Dispatch to the appropriate formatter based on format string.

    Args:
        records: List of PrinterRecord objects to format.
        fmt: One of "table", "json", or "csv".

    Returns:
        Formatted string output.

    Raises:
        ValueError: If fmt is not a recognised format.
    """
    formatters = {
        "table": format_table,
        "json": format_json,
        "csv": format_csv,
    }
    formatter = formatters.get(fmt)
    if formatter is None:
        raise ValueError(f"Unknown output format: {fmt!r}. Expected one of: table, json, csv")
    return formatter(records)
