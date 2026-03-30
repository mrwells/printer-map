# printer-map

A Python CLI tool that discovers printers on your local network using mDNS, SNMP, and IPP protocols, then reports their capabilities.

Useful for debugging printer setups, auditing printer fleets, and verifying printer configurations.

## Features

- **mDNS discovery** — finds Bonjour/AirPrint printers via `_ipp._tcp`, `_ipps._tcp`, and `_pdl-datastream._tcp`
- **SNMP discovery** — queries Printer-MIB OIDs to identify SNMP-managed printers
- **IPP capability querying** — retrieves supported formats, resolutions, color, and duplex via Get-Printer-Attributes
- **Multiple output formats** — table (default), JSON, or CSV
- **Concurrent scanning** — mDNS and SNMP run in parallel, results are merged and deduplicated by IP

## Installation

```bash
pip install -e .
```

For development (includes test dependencies):

```bash
pip install -e ".[dev]"
```

### Requirements

- Python 3.10+
- Network access to printers on the local subnet

## Usage

```bash
# Scan the local network
printer-map scan

# Scan specific targets
printer-map scan --target 192.168.1.0/24
printer-map scan --target 10.0.0.50 --target 10.0.0.51

# Change output format
printer-map scan --format json
printer-map scan --format csv

# Adjust timeout and SNMP community string
printer-map scan --timeout 10 --community private

# Verbose logging
printer-map scan --verbose
```

### Example output

```
Printer 1: HP Smart Tank 7000 series [7A4900]
  IP:          10.10.10.196
  Hostname:    HPD862E1.local.
  Protocols:   mDNS
  Formats:     application/vnd.hp-PCL, image/jpeg, image/urf, image/pwg-raster
  Resolution:  300x300dpi, 600x600dpi, 1200x1200dpi
  Color:       True
  Duplex:      True
```

### CLI options

| Option | Description | Default |
|---|---|---|
| `--target` | IP address, CIDR range, or hostname (repeatable) | local subnet |
| `--timeout` | Discovery timeout in seconds | `5.0` |
| `--community` | SNMP community string | `public` |
| `--format` | Output format: `table`, `json`, `csv` | `table` |
| `--verbose` | Enable detailed logging to stderr | off |
| `--version` | Show version and exit | — |

## Development

### Running tests

```bash
pytest
```

The test suite includes both unit tests and property-based tests (via [Hypothesis](https://hypothesis.readthedocs.io/)).

### Project structure

```
src/printer_map/
├── main.py             # CLI entry point
├── config.py           # Argument parsing and ScanConfig
├── models.py           # PrinterRecord dataclass
├── mdns_discovery.py   # mDNS service browsing
├── snmp_discovery.py   # SNMP printer querying
├── ipp_client.py       # IPP Get-Printer-Attributes
├── scanner.py          # Orchestration, merge, dedup
└── formatters.py       # Table, JSON, CSV output
```

## License

MIT
