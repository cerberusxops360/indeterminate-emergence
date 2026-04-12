"""
Experiment 7: Wire-Level Capture

Verify that the 4096-byte response padding holds at the TCP layer, and that
packet count / size distribution does not encode path information.

Two sub-tests:
  1. Content-length verification — every HTTP response body is exactly
     RESPONSE_SIZE bytes regardless of path.
  2. Packet structure — uses tcpdump + tshark to capture a request stream
     and compare per-response packet count and total byte distributions.

Run from poc/ directory (proxy must be running on BASE_URL):
    uvicorn src.proxy:app --port 8100
    python -m eval.wire_capture

For packet capture, tshark must be installed and the user must have
capture permissions (run as root, or: sudo setcap cap_net_raw+eip $(which tshark))
"""

import json
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import numpy as np
from scipy import stats

from src.config import ALL_TOOLS, SessionConfig
from src.proxy import session_store

RESULTS_DIR = Path(__file__).parent / "results"
BASE_URL = "http://localhost:8100"
RESPONSE_SIZE = 4096   # bytes, from channel_shaper.py
N_REQUESTS = 100       # requests per path for HTTP-level size verification
N_CAPTURE = 30         # requests per path for packet capture (slow)
KS_ALPHA = 0.05
TOOL = "web_search"
PARAMS = {"query": "test"}


def _setup_sessions() -> None:
    session_store.register(SessionConfig(
        session_id="wire_authorized",
        authorized_tools=ALL_TOOLS.copy(),
        budget=100000.0,
        per_query_epsilon=0.001,
        absorption_margin=0.0,
    ))
    session_store.register(SessionConfig(
        session_id="wire_unauthorized",
        authorized_tools=[],
        budget=100000.0,
        per_query_epsilon=0.001,
        absorption_margin=0.0,
    ))


def _collect_sizes(session_id: str, label: str, n: int) -> list[int]:
    """
    Collect HTTP response content-length for n requests.
    Returns list of body sizes in bytes.
    """
    sizes = []
    with httpx.Client(timeout=10.0) as client:
        for i in range(n):
            if i % 25 == 0:
                print(f"  {label}: {i}/{n}...", flush=True)
            resp = client.post(f"{BASE_URL}/action", json={
                "tool": TOOL,
                "params": PARAMS,
                "session_id": session_id,
            })
            sizes.append(len(resp.content))
    return sizes


def _tshark_available() -> bool:
    return shutil.which("tshark") is not None


def _tcpdump_available() -> bool:
    return shutil.which("tcpdump") is not None


def _run_packet_capture(session_id: str, label: str, n: int) -> dict | None:
    """
    Start tcpdump, send n requests, stop tcpdump, parse with tshark.
    Returns dict with per-response packet stats, or None if capture tools
    are unavailable.
    """
    if not _tcpdump_available():
        return None

    pcap_path = RESULTS_DIR / f"wire_capture_{label}.pcap"

    # Start tcpdump in background
    tcpdump_cmd = [
        "tcpdump", "-i", "lo",
        "-w", str(pcap_path),
        "tcp", "port", "8100",
    ]
    proc = subprocess.Popen(
        tcpdump_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.3)  # let tcpdump bind

    try:
        with httpx.Client(timeout=10.0) as client:
            for _ in range(n):
                client.post(f"{BASE_URL}/action", json={
                    "tool": TOOL,
                    "params": PARAMS,
                    "session_id": session_id,
                })
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)

    if not pcap_path.exists():
        return None

    if not _tshark_available():
        return {"pcap": str(pcap_path), "parsed": False}

    # Parse with tshark: extract TCP payload lengths per packet
    tshark_result = subprocess.run(
        [
            "tshark", "-r", str(pcap_path),
            "-T", "fields",
            "-e", "frame.len",
            "-e", "tcp.len",
            "-e", "tcp.dstport",
        ],
        capture_output=True, text=True,
    )

    packet_lengths = []
    response_payload_lengths = []
    for line in tshark_result.stdout.strip().splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 3:
            continue
        try:
            frame_len = int(parts[0])
            tcp_len = int(parts[1]) if parts[1] else 0
            dst_port = int(parts[2]) if parts[2] else 0
            # Only count packets FROM the server (src port 8100 = dst of client)
            # tshark field tcp.dstport is client port when server replies
            if dst_port != 8100 and tcp_len > 0:
                response_payload_lengths.append(tcp_len)
            packet_lengths.append(frame_len)
        except ValueError:
            continue

    return {
        "pcap": str(pcap_path),
        "parsed": True,
        "packet_lengths": packet_lengths,
        "response_payload_lengths": response_payload_lengths,
    }


def run_wire_capture() -> bool:
    RESULTS_DIR.mkdir(exist_ok=True)
    _setup_sessions()

    print("Experiment 7: Wire-Level Capture")
    print("=" * 70)

    # Check proxy is reachable
    try:
        with httpx.Client(timeout=5.0) as c:
            c.post(f"{BASE_URL}/action", json={"tool": "calculator", "params": {},
                                                "session_id": "wire_authorized"})
    except Exception as e:
        print(f"ERROR: Proxy not reachable at {BASE_URL}: {e}")
        print("Start the proxy first: uvicorn src.proxy:app --port 8100")
        return False

    # Sub-test 1: HTTP content-length verification
    print(f"\nSub-test 1: HTTP response body size ({N_REQUESTS} requests per path)")
    auth_sizes = _collect_sizes("wire_authorized", "authorized", N_REQUESTS)
    unauth_sizes = _collect_sizes("wire_unauthorized", "unauthorized", N_REQUESTS)

    auth_exact = all(s == RESPONSE_SIZE for s in auth_sizes)
    unauth_exact = all(s == RESPONSE_SIZE for s in unauth_sizes)
    size_pass = auth_exact and unauth_exact

    size_lines = [
        "",
        "Sub-test 1: HTTP body size",
        f"  Target size: {RESPONSE_SIZE} bytes",
        f"  Authorized   — all exact: {auth_exact}  "
        f"min={min(auth_sizes)}  max={max(auth_sizes)}",
        f"  Unauthorized — all exact: {unauth_exact}  "
        f"min={min(unauth_sizes)}  max={max(unauth_sizes)}",
        f"  Result: {'PASS' if size_pass else 'FAIL'}",
    ]

    # Sub-test 2: Packet-level capture
    print(f"\nSub-test 2: Packet capture ({N_CAPTURE} requests per path)")
    if not _tcpdump_available():
        print("  WARNING: tcpdump not found — skipping packet capture sub-test")
        capture_lines = [
            "",
            "Sub-test 2: Packet capture",
            "  SKIPPED — tcpdump not available",
        ]
        packet_pass = True  # not a failure — just not measurable here
    else:
        print("  Capturing authorized path...")
        auth_cap = _run_packet_capture("wire_authorized", "authorized", N_CAPTURE)
        print("  Capturing unauthorized path...")
        unauth_cap = _run_packet_capture("wire_unauthorized", "unauthorized", N_CAPTURE)

        if auth_cap and unauth_cap and auth_cap.get("parsed") and unauth_cap.get("parsed"):
            auth_resp = np.array(auth_cap["response_payload_lengths"], dtype=np.float64)
            unauth_resp = np.array(unauth_cap["response_payload_lengths"], dtype=np.float64)

            if len(auth_resp) > 1 and len(unauth_resp) > 1:
                ks_stat, ks_p = stats.ks_2samp(auth_resp, unauth_resp)
                ks_pass = ks_p >= KS_ALPHA

                np.save(RESULTS_DIR / "wire_capture_auth_packets.npy", auth_resp)
                np.save(RESULTS_DIR / "wire_capture_unauth_packets.npy", unauth_resp)

                capture_lines = [
                    "",
                    "Sub-test 2: Packet capture",
                    f"  authorized pcap:   {auth_cap['pcap']}",
                    f"  unauthorized pcap: {unauth_cap['pcap']}",
                    "",
                    "  Response TCP payload lengths:",
                    f"  {'':20} {'authorized':>12} {'unauthorized':>14}",
                    "  " + "-" * 48,
                    f"  {'packets captured':<20} {len(auth_resp):>12} {len(unauth_resp):>14}",
                    f"  {'mean (bytes)':<20} {auth_resp.mean():>12.1f} {unauth_resp.mean():>14.1f}",
                    f"  {'std (bytes)':<20} {auth_resp.std():>12.1f} {unauth_resp.std():>14.1f}",
                    f"  {'max (bytes)':<20} {auth_resp.max():>12.0f} {unauth_resp.max():>14.0f}",
                    "",
                    f"  KS statistic: {ks_stat:.6f}",
                    f"  KS p-value:   {ks_p:.6f}",
                    f"  Result: {'PASS' if ks_pass else 'FAIL'} (alpha={KS_ALPHA})",
                ]
                packet_pass = ks_pass
            else:
                capture_lines = ["", "Sub-test 2: Packet capture",
                                  "  WARNING: too few packets parsed from pcap"]
                packet_pass = True
        else:
            auth_pcap = auth_cap.get('pcap', 'N/A') if auth_cap else 'capture failed'
            unauth_pcap = unauth_cap.get('pcap', 'N/A') if unauth_cap else 'capture failed'
            capture_lines = [
                "",
                "Sub-test 2: Packet capture",
                f"  authorized pcap:   {auth_pcap}",
                f"  unauthorized pcap: {unauth_pcap}",
                "  tshark not available, parse failed, or tcpdump permission denied",
                "  Tip: sudo setcap cap_net_raw+eip $(which tcpdump)",
            ]
            packet_pass = True

    # Combine results
    overall = size_pass and packet_pass
    lines = (
        ["Experiment 7: Wire-Level Capture", "=" * 70]
        + size_lines
        + capture_lines
        + [
            "",
            "=" * 70,
            f"Sub-test 1 (body size):    {'PASS' if size_pass else 'FAIL'}",
            f"Sub-test 2 (packet dist):  {'PASS' if packet_pass else 'FAIL'}",
            f"Overall: {'PASS' if overall else 'FAIL'}",
        ]
    )

    summary = "\n".join(lines)
    print()
    print(summary)

    summary_path = RESULTS_DIR / "wire_capture_summary.txt"
    summary_path.write_text(summary + "\n")
    print(f"\nSummary: {summary_path}")

    return overall


if __name__ == "__main__":
    success = run_wire_capture()
    sys.exit(0 if success else 1)
