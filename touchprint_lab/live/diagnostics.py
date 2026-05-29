from __future__ import annotations

import argparse
import json
import socket
from dataclasses import dataclass
from typing import Iterable

from touchprint_lab.live.telemetry_server import _suggested_lan_ip


@dataclass(slots=True)
class PortProbeResult:
    host: str
    port: int
    reachable: bool
    error: str | None = None


def detect_lan_ips() -> list[str]:
    candidates: list[str] = []
    for endpoint in [("8.8.8.8", 80), ("1.1.1.1", 80)]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
                udp_socket.connect(endpoint)
                local_ip = udp_socket.getsockname()[0]
                if local_ip and not local_ip.startswith("127.") and local_ip not in candidates:
                    candidates.append(local_ip)
        except OSError:
            continue

    try:
        hostname = socket.gethostname()
        hostname_ip = socket.gethostbyname(hostname)
        if hostname_ip and not hostname_ip.startswith("127.") and hostname_ip not in candidates:
            candidates.append(hostname_ip)
    except OSError:
        pass

    return candidates


def probe_port(host: str, port: int, timeout: float = 1.0) -> PortProbeResult:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return PortProbeResult(host=host, port=port, reachable=True)
    except OSError as exc:
        return PortProbeResult(host=host, port=port, reachable=False, error=str(exc))


def classify_probe_error(error: str | None) -> str:
    if not error:
        return "reachable"
    lowered = error.lower()
    if "permission" in lowered or "operation not permitted" in lowered:
        return "permission likely denied"
    if "no route" in lowered or "network is unreachable" in lowered:
        return "no route"
    if "timed out" in lowered:
        return "timeout"
    if "refused" in lowered:
        return "refused"
    if "name or service not known" in lowered or "nodename nor servname provided" in lowered:
        return "invalid host"
    return "unreachable"


def print_diagnostics(host: str, port: int) -> None:
    lan_ips = detect_lan_ips()
    suggested_ip = _suggested_lan_ip()
    local_probe = probe_port("127.0.0.1", port)
    lan_probe_host = suggested_ip if suggested_ip != "unavailable" else (lan_ips[0] if lan_ips else None)
    lan_probe = probe_port(lan_probe_host, port) if lan_probe_host else None
    host_probe = probe_port(host, port) if host and host != "0.0.0.0" else None

    print("Touchprint Live Telemetry Diagnostics")
    print(f"Server bind host: {host}")
    print(f"Server port: {port}")
    if host == "0.0.0.0":
        print("Binding mode: all interfaces (recommended for real devices)")
    else:
        print("Binding mode: specific host")
    print(f"Detected LAN IPs: {json.dumps(lan_ips or ['unavailable'])}")
    print(f"Suggested iOS host: {suggested_ip if suggested_ip != 'unavailable' else (lan_ips[0] if lan_ips else 'unavailable')}")
    print(f"127.0.0.1:{port} probe: {'reachable' if local_probe.reachable else classify_probe_error(local_probe.error)}")
    if lan_probe is not None:
        print(f"{lan_probe.host}:{port} probe: {'reachable' if lan_probe.reachable else classify_probe_error(lan_probe.error)}")
    if host_probe is not None:
        print(f"{host}:{port} probe: {'reachable' if host_probe.reachable else classify_probe_error(host_probe.error)}")
    print("Server binding guidance:")
    print("- Bind the Python server to 0.0.0.0 for real devices.")
    print("- On iPhone/iPad, use the Mac LAN IP, not 127.0.0.1.")
    print("- If the probe is refused, check macOS Firewall and Python local network permissions.")
    print("- If the probe times out, check Wi-Fi client isolation or VPN.")
    print("Test command hint:")
    print(f"nc -vz {suggested_ip if suggested_ip != 'unavailable' else (lan_ips[0] if lan_ips else '<MacLANIP>')} {port}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print Touchprint live telemetry reachability diagnostics.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    print_diagnostics(args.host, args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
