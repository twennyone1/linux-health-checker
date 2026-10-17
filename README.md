# Linux Health Checker Pro

A lightweight, read-only Linux diagnostics tool written in Python.

## Features

- System and uptime information
- Disk usage checks
- Memory usage checks
- System load averages
- Failed systemd units
- Optional Docker diagnostics
- Basic checks of sensitive file permissions and SSH configuration
- JSON report export
- Summary-only output mode

## Requirements

- Linux
- Python 3.10 or newer recommended
- Docker is optional

## Usage

Run diagnostics:

    python3 healthcheck.py

Save a JSON report:

    python3 healthcheck.py --json report.json

Show only non-OK results:

    python3 healthcheck.py --quiet

## Safety

The tool is designed for read-only diagnostics. It does not automatically
change system settings or repair detected problems.

Some checks may return UNKNOWN when permissions, tools, or system features
are unavailable. Results are diagnostic hints, not a complete security audit.

## License

MIT
