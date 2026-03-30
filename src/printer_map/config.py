"""CLI configuration: argparse parser and ScanConfig dataclass."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from printer_map import __version__


@dataclass
class ScanConfig:
    """CLI configuration for a scan invocation."""

    targets: list[str] = field(default_factory=list)
    timeout: float = 5.0
    community: str = "public"
    output_format: str = "table"
    verbose: bool = False
    version: bool = False


def build_parser() -> argparse.ArgumentParser:
    """Create the argparse parser with the ``scan`` subcommand and all options."""

    parser = argparse.ArgumentParser(
        prog="printer-map",
        description="Discover printers on the local network using mDNS, SNMP, and IPP.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Scan the network for printers")
    scan_parser.add_argument(
        "--target",
        action="append",
        default=None,
        dest="targets",
        metavar="TARGET",
        help="IP address, CIDR range, or hostname to scan (repeatable)",
    )
    scan_parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Discovery timeout in seconds (default: 5.0)",
    )
    scan_parser.add_argument(
        "--community",
        default="public",
        help='SNMP community string (default: "public")',
    )
    scan_parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        dest="output_format",
        help="Output format (default: table)",
    )
    scan_parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable detailed logging to stderr",
    )

    return parser


def load_config(argv: list[str] | None = None) -> ScanConfig:
    """Parse *argv* (or ``sys.argv[1:]``) and return a :class:`ScanConfig`."""

    parser = build_parser()
    args = parser.parse_args(argv)

    # Display help when invoked without a command
    if args.command is None:
        parser.print_help()
        raise SystemExit(0)

    return ScanConfig(
        targets=args.targets or [],
        timeout=args.timeout,
        community=args.community,
        output_format=args.output_format,
        verbose=args.verbose,
        version=False,
    )
