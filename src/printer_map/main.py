"""Main entry point for the printer-scanner CLI."""

from __future__ import annotations

import asyncio
import logging
import sys


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: parse config, run scan, format and print output."""
    try:
        from printer_map.config import load_config
        from printer_map.formatters import format_output
        from printer_map.scanner import run_scan
    except ImportError as exc:
        print(f"Missing required dependency: {exc.name or exc}", file=sys.stderr)
        raise SystemExit(1)

    try:
        config = load_config(argv)
    except SystemExit:
        raise

    # Set up logging: verbose → DEBUG to stderr, normal → WARNING to stderr
    level = logging.DEBUG if config.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    results = asyncio.run(run_scan(config))

    if not results:
        print("No printers found.", file=sys.stderr)
        raise SystemExit(0)

    output = format_output(results, config.output_format)
    print(output)


if __name__ == "__main__":
    main()
