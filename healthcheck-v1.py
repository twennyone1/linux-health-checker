#!/usr/bin/env python3

import os
import shutil
import platform
import subprocess
from datetime import datetime

def read_memory():
    try:
        values = {}
        with open("/proc/meminfo") as file:
            for line in file:
                key, value = line.split(":", 1)
                if key in ("MemTotal", "MemAvailable"):
                    values[key] = int(value.strip().split()[0])

        total = values["MemTotal"] / 1024
        available = values["MemAvailable"] / 1024
        used_percent = (1 - available / total) * 100
        return total, available, used_percent
    except (OSError, KeyError, ValueError):
        return None, None, None

def main():
    print("=" * 52)
    print("        LINUX HEALTH CHECK REPORT")
    print("=" * 52)
    print(f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}")
    print(f"Hostname:  {platform.node()}")
    print(f"OS:        {platform.platform()}")

    print("\n[ DISK USAGE ]")
    for path in ("/", "/home"):
        if not os.path.exists(path):
            continue
        usage = shutil.disk_usage(path)
        used = usage.used / usage.total * 100
        status = "WARNING" if used >= 85 else "OK"
        print(f"{path}: {used:.1f}% used — {status}")

    print("\n[ MEMORY ]")
    total, available, used = read_memory()
    if total is not None:
        status = "WARNING" if used >= 90 else "OK"
        print(f"Total: {total:.0f} MiB")
        print(f"Available: {available:.0f} MiB")
        print(f"Used: {used:.1f}% — {status}")
    else:
        print("Memory information unavailable.")

    print("\n[ SYSTEM LOAD ]")
    try:
        print("1, 5, 15 min:", ", ".join(
            f"{value:.2f}" for value in os.getloadavg()
        ))
    except (AttributeError, OSError):
        print("Load average unavailable.")

    print("\n[ SYSTEMD FAILED SERVICES ]")
    try:
        result = subprocess.run(
            ["systemctl", "--failed", "--no-legend", "--plain"],
            capture_output=True, text=True, timeout=10, check=False
        )
        if result.returncode == 0:
            failures = [line for line in result.stdout.splitlines() if line.strip()]
            if failures:
                for failure in failures:
                    print(failure)
            else:
                print("No failed services reported.")
        else:
            print("Could not query systemd services.")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("systemctl unavailable.")

    print("\nNote: This is a basic diagnostic, not a security audit.")
    print("=" * 52)

if __name__ == "__main__":
    main()
