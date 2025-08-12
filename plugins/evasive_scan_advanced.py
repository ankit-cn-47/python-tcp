# How It Works

# - Hosts and ports lists are fully randomized on each invocation, defeating simple rate-based alarms. 
# - Each socket uses a random timeout between 300 ms and 1.2 s. 
# - After each attempt, the plugin sleeps a base delay (0.1 – 0.8 s) plus up to 200 ms jitter. 
# - Common service ports (HTTP, SSH) are probed with a minimal real-traffic payload to look like a genuine client.

# Usage Example
# /plugin evasivescanadvanced 192.168.1.10-12,192.168.1.20 22,80,443,8080

# Sample output:
# 192.168.1.11: [22, 80]
# 192.168.1.10: No open ports
# 192.168.1.12: [443]
# 192.168.1.20: [22, 8080]

import socket
import random
import time
from typing import List

name = "evasive_scan_advanced"

# Define tiny payloads to mimic real clients on known ports
LEGITIMATE_TRAFFIC = {
    80:  b"GET / HTTP/1.1\r\nHost: example.com\r\nUser-Agent: Mozilla/5.0\r\n\r\n",
    22:  b"SSH-2.0-OpenSSH_7.9\r\n",
    443: None  # TLS handshake is heavy; skipping payload
}

def expand_hosts(hosts_arg: str) -> List[str]:
    """
    Supports comma-separated hosts and simple last-octet ranges:
    192.168.1.10,192.168.1.20-25 → ['192.168.1.10','192.168.1.20',...,'192.168.1.25']
    """
    out = []
    for part in hosts_arg.split(","):
        if "-" in part:
            start, end = part.split("-")
            base = ".".join(start.split(".")[:-1])
            lo = int(start.split(".")[-1])
            hi = int(end.split(".")[-1])
            out += [f"{base}.{i}" for i in range(lo, hi + 1)]
        else:
            out.append(part)
    return out

def run(args: List[str]) -> str:
    """
    Advanced evasive port scanner
    Usage: /plugin evasivescanadvanced <hosts> <ports>
      hosts:   comma-separated IPs or a.b.c.d-e (last-octet range)
      ports:   comma-separated port numbers (e.g. 22,80,443)
    """
    if len(args) < 2:
        return ("Usage: /plugin evasivescanadvanced <hosts> <ports>\n"
                "Example: /plugin evasivescanadvanced 192.168.1.10-12,192.168.1.20 22,80,443")

    hosts = expand_hosts(args[0])
    ports = [int(p) for p in args[1].split(",")]

    # Shuffle total host list once
    random.shuffle(hosts)

    results = []
    for host in hosts:
        open_ports = []

        # Shuffle ports anew for each host
        port_list = ports.copy()
        random.shuffle(port_list)

        for port in port_list:
            # Randomize timeout (jitter) and inter-scan delay
            timeout = random.uniform(0.3, 1.2)
            delay   = random.uniform(0.1, 0.8)

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)

            try:
                sock.connect((host, port))

                # If it's a “web” or “ssh” port, send a tiny legit payload
                payload = LEGITIMATE_TRAFFIC.get(port)
                if payload:
                    sock.sendall(payload)
                    # wait briefly after sending
                    time.sleep(random.uniform(0.02, 0.15))

                open_ports.append(port)

            except socket.error:
                # closed/filtered
                pass

            finally:
                sock.close()

            # Add a small extra random jitter before next attempt
            time.sleep(delay + random.uniform(0, 0.2))

        results.append(f"{host}: {open_ports if open_ports else 'No open ports'}")

    return "\n".join(results)
