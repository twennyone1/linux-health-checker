
#!/usr/bin/env python3
"""Linux Health Checker Pro — read-only diagnostics."""

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = "2.0.0"


class HealthChecker:
    def __init__(self):
        self.results = []
        self.started = time.monotonic()

    def add(self, category, name, status, details, recommendation=None):
        self.results.append({
            "category": category,
            "check": name,
            "status": status,
            "details": str(details),
            "recommendation": recommendation,
        })

    def command(self, args, timeout=5):
        try:
            result = subprocess.run(
                args, capture_output=True, text=True,
                timeout=timeout, check=False
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except FileNotFoundError:
            return 127, "", "Command not installed"
        except subprocess.TimeoutExpired:
            return 124, "", "Command timed out"
        except OSError as exc:
            return 1, "", str(exc)

    def check_system(self):
        self.add("system", "Hostname", "OK", socket.gethostname())
        self.add("system", "Operating system", "OK", platform.platform())
        self.add("system", "Python version", "OK", platform.python_version())

        try:
            uptime = float(Path("/proc/uptime").read_text().split()[0])
            self.add(
                "system", "Uptime", "OK",
                f"{uptime / 86400:.2f} days"
            )
        except (OSError, ValueError, IndexError):
            self.add("system", "Uptime", "UNKNOWN", "Unavailable")

    def check_disks(self):
        paths = {"/"}
        if Path("/home").exists():
            paths.add("/home")

        try:
            for line in Path("/proc/mounts").read_text().splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1].startswith("/"):
                    mount = parts[1].replace("\\040", " ")
                    if mount in ("/", "/home", "/var", "/tmp"):
                        paths.add(mount)
        except OSError:
            pass

        for path in sorted(paths):
            if not os.path.exists(path):
                continue
            try:
                usage = shutil.disk_usage(path)
                percent = usage.used / usage.total * 100
                status = "CRITICAL" if percent >= 95 else (
                    "WARNING" if percent >= 85 else "OK"
                )
                recommendation = (
                    "Investigate large files and logs."
                    if status != "OK" else None
                )
                self.add(
                    "storage", f"Disk {path}", status,
                    f"{percent:.1f}% used; "
                    f"{usage.free / (1024**3):.2f} GiB free",
                    recommendation
                )
            except OSError as exc:
                self.add("storage", f"Disk {path}", "UNKNOWN", exc)

    def check_memory(self):
        try:
            mem = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, value = line.split(":", 1)
                mem[key] = int(value.strip().split()[0])

            total = mem["MemTotal"]
            available = mem.get("MemAvailable")
            if not total or available is None:
                raise ValueError("Required memory fields unavailable")

            used = (total - available) / total * 100
            status = "CRITICAL" if used >= 95 else (
                "WARNING" if used >= 90 else "OK"
            )
            self.add(
                "memory", "RAM usage", status,
                f"{used:.1f}% used; "
                f"{available / 1024:.0f} MiB available",
                "Inspect memory-heavy processes if usage stays high."
                if status != "OK" else None
            )
        except (OSError, ValueError, KeyError, IndexError) as exc:
            self.add("memory", "RAM usage", "UNKNOWN", exc)

    def check_load(self):
        try:
            load = os.getloadavg()
            cpus = os.cpu_count() or 1
            one_minute_per_cpu = load[0] / cpus
            status = "WARNING" if one_minute_per_cpu >= 1.5 else "OK"
            self.add(
                "performance", "Load average", status,
                f"1/5/15 min: {load[0]:.2f}, {load[1]:.2f}, "
                f"{load[2]:.2f}; CPUs: {cpus}",
                "Investigate CPU and I/O pressure if sustained."
                if status != "OK" else None
            )
        except (OSError, AttributeError):
            self.add(
                "performance", "Load average", "UNKNOWN",
                "Unavailable on this platform"
            )

    def check_services(self):
        if not shutil.which("systemctl"):
            self.add(
                "services", "systemd", "UNKNOWN",
                "systemctl not installed"
            )
            return

        code, out, err = self.command([
            "systemctl", "--failed", "--no-legend", "--plain"
        ])
        if code != 0:
            self.add(
                "services", "Failed systemd units", "UNKNOWN",
                err or "Could not query systemd"
            )
        else:
            failures = [line for line in out.splitlines() if line.strip()]
            self.add(
                "services", "Failed systemd units",
                "WARNING" if failures else "OK",
                "\n".join(failures) if failures
                else "No failed units reported",
                "Inspect failed units with systemctl status."
                if failures else None
            )

    def check_docker(self):
        if not shutil.which("docker"):
            self.add(
                "containers", "Docker", "INFO",
                "Docker CLI not installed; skipped"
            )
            return

        code, out, err = self.command(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            timeout=8
        )
        if code != 0:
            self.add(
                "containers", "Docker daemon", "UNKNOWN",
                err or "Docker unavailable or permission denied"
            )
            return

        self.add("containers", "Docker daemon", "OK", out)
        code, out, err = self.command([
            "docker", "ps", "-a",
            "--format", "{{.Names}} | {{.Status}}"
        ])
        if code != 0:
            self.add("containers", "Container list", "UNKNOWN", err)
        else:
            lines = [x for x in out.splitlines() if x.strip()]
            self.add(
                "containers", "Containers",
                "OK", "\n".join(lines) if lines else "No containers found"
            )

    def check_permissions(self):
        path = Path("/etc/shadow")
        if not path.exists():
            self.add(
                "security", "/etc/shadow permissions", "UNKNOWN",
                "File not found"
            )
            return

        try:
            mode = path.stat().st_mode & 0o777
            safe = (mode & 0o007) == 0 and (mode & 0o020) == 0
            self.add(
                "security", "/etc/shadow permissions",
                "OK" if safe else "WARNING",
                f"Mode: {mode:04o}",
                "Review permissions with your distribution's guidance."
                if not safe else None
            )
        except OSError as exc:
            self.add(
                "security", "/etc/shadow permissions", "UNKNOWN", exc
            )

    def check_ssh(self):
        config = Path("/etc/ssh/sshd_config")
        if not config.exists():
            self.add(
                "security", "SSH server configuration", "INFO",
                "sshd_config not found; SSH server may not be installed"
            )
            return

        try:
            values = {}
            for line in config.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2:
                    values[parts[0].lower()] = parts[1].strip()

            root_login = values.get("permitrootlogin")
            if root_login is None:
                self.add(
                    "security", "SSH root login setting", "UNKNOWN",
                    "No explicit setting found; included files may affect it",
                    "Review the effective configuration with sshd -T."
                )
            else:
                status = (
                    "WARNING" if root_login.lower() in ("yes", "without-password")
                    else "OK"
                )
                self.add(
                    "security", "SSH root login setting", status,
                    f"Configured value: {root_login}",
                    "Review whether direct root SSH login is necessary."
                    if status == "WARNING" else None
                )
        except OSError as exc:
            self.add("security", "SSH configuration", "UNKNOWN", exc)

    def run(self):
        self.check_system()
        self.check_disks()
        self.check_memory()
        self.check_load()
        self.check_services()
        self.check_docker()
        self.check_permissions()
        self.check_ssh()
        return self.results


def main():
    parser = argparse.ArgumentParser(
        description="Read-only Linux health diagnostics"
    )
    parser.add_argument("--json", help="Write full report to this JSON file")
    parser.add_argument("--quiet", action="store_true",
                        help="Only print the summary")
    args = parser.parse_args()

    checker = HealthChecker()
    results = checker.run()

    counts = {
        level: sum(r["status"] == level for r in results)
        for level in ("CRITICAL", "WARNING", "UNKNOWN", "INFO", "OK")
    }

    report = {
        "tool": "Linux Health Checker Pro",
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "results": results,
        "summary": counts,
        "duration_seconds": round(time.monotonic() - checker.started, 3),
    }

    print(f"\nLinux Health Checker Pro v{VERSION}")
    print(f"Host: {report['hostname']}")
    print("-" * 65)

    for item in results:
        if args.quiet and item["status"] == "OK":
            continue
        print(f"[{item['status']}] {item['category']}: {item['check']}")
        print(f"  {item['details']}")
        if item["recommendation"]:
            print(f"  Suggestion: {item['recommendation']}")

    print("-" * 65)
    print("Summary:", " | ".join(
        f"{key}={value}" for key, value in counts.items()
    ))
    print(f"Duration: {report['duration_seconds']} seconds")

    if args.json:
        try:
            Path(args.json).write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n"
            )
            print(f"JSON report saved to: {args.json}")
        except OSError as exc:
            parser.error(f"Cannot write JSON report: {exc}")


if __name__ == "__main__":
    main()
