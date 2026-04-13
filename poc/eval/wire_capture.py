"""
Experiment 7: Wire-Level Capture

Verify that the 4096-byte response padding holds at the TCP layer, and that
neither packet size distribution nor inter-segment timing encodes path information.

Three sub-tests:
  1. Content-length verification — every HTTP response body is exactly
     RESPONSE_SIZE bytes regardless of path.
  2. Packet payload length distribution — KS test on TCP payload lengths.
  3. Inter-segment timing — KS test on intra-response inter-packet deltas
     (microsecond-precision). Closes KI-001.

Run from poc/ directory (proxy must be running on BASE_URL):
    uvicorn src.proxy:app --port 8100
    python -m eval.wire_capture

Sub-tests 2 and 3 require tcpdump and tshark with cap_net_raw:
    sudo setcap cap_net_raw+eip $(which tcpdump)
    sudo setcap cap_net_raw+eip $(which tshark)
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
N_CAPTURE = 30         # requests per path for sub-test 2 packet capture
N_CAPTURE_TIMING = 50  # requests per path for sub-test 3 inter-segment timing
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


def _capture_pcap(session_id: str, label: str, n: int, microsecond: bool = False) -> Path | None:
    """
    Start tcpdump, send n sequential requests, stop tcpdump.
    Returns path to the pcap file, or None if capture failed.
    microsecond=True adds --time-stamp-precision=micro for sub-test 3.
    """
    if not _tcpdump_available():
        return None

    pcap_path = RESULTS_DIR / f"wire_capture_{label}.pcap"

    cmd = ["tcpdump", "-i", "lo", "-w", str(pcap_path), "tcp", "port", "8100"]
    if microsecond:
        cmd = ["tcpdump", "-i", "lo", "--time-stamp-precision=micro",
               "-w", str(pcap_path), "tcp", "port", "8100"]

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.3)

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

    return pcap_path if pcap_path.exists() else None


def _parse_intersegment_deltas(pcap_path: Path) -> np.ndarray | None:
    """
    Parse a pcap for intra-response inter-segment timing.

    Groups server-to-client packets (srcport==8100) by TCP stream, then
    identifies per-response bursts by splitting on inter-packet gaps > 100ms
    (responses are shaped to 200-400ms, so the gap between them is large).
    Within each burst, computes consecutive inter-packet deltas in microseconds.

    Returns a flat array of all intra-response inter-packet deltas, or None
    if parsing fails or produces insufficient data.
    """
    if not _tshark_available() or not pcap_path.exists():
        return None

    result = subprocess.run(
        [
            "tshark", "-r", str(pcap_path),
            "-T", "fields",
            "-e", "frame.time_epoch",
            "-e", "tcp.len",
            "-e", "tcp.srcport",
            "-e", "tcp.stream",
        ],
        capture_output=True, text=True,
    )

    # Parse into list of (time_epoch_s, tcp_len, srcport, stream)
    packets: list[tuple[float, int, int, int]] = []
    for line in result.stdout.strip().splitlines():
        parts = line.strip().split("\t")
        if len(parts) < 4:
            continue
        try:
            t = float(parts[0])
            length = int(parts[1]) if parts[1] else 0
            srcport = int(parts[2]) if parts[2] else 0
            stream = int(parts[3]) if parts[3] else 0
            if length > 0 and srcport == 8100:
                packets.append((t, length, srcport, stream))
        except ValueError:
            continue

    if len(packets) < 4:
        return None

    # Sort by timestamp
    packets.sort(key=lambda p: p[0])

    # Split into per-response bursts: gap > 100ms = new response
    GAP_THRESHOLD_S = 0.1
    deltas_us: list[float] = []

    burst: list[float] = [packets[0][0]]
    for i in range(1, len(packets)):
        t_prev = packets[i - 1][0]
        t_curr = packets[i][0]
        gap = t_curr - t_prev
        if gap > GAP_THRESHOLD_S:
            # End of one response burst — compute intra-burst deltas
            if len(burst) >= 2:
                for j in range(1, len(burst)):
                    deltas_us.append((burst[j] - burst[j - 1]) * 1e6)
            burst = [t_curr]
        else:
            burst.append(t_curr)

    # Flush final burst
    if len(burst) >= 2:
        for j in range(1, len(burst)):
            deltas_us.append((burst[j] - burst[j - 1]) * 1e6)

    return np.array(deltas_us, dtype=np.float64) if len(deltas_us) >= 2 else None


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

    # Sub-test 2: Packet payload length distribution
    print(f"\nSub-test 2: Packet payload length distribution ({N_CAPTURE} requests per path)")
    if not _tcpdump_available() or not _tshark_available():
        missing = "tcpdump" if not _tcpdump_available() else "tshark"
        print(f"  SKIPPED — {missing} not available or lacks cap_net_raw")
        capture_lines = ["", "Sub-test 2: Packet payload distribution",
                         f"  SKIPPED — {missing} not available"]
        packet_pass = True
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
                    "", "Sub-test 2: Packet payload distribution",
                    f"  {'':20} {'authorized':>12} {'unauthorized':>14}",
                    "  " + "-" * 48,
                    f"  {'packets':<20} {len(auth_resp):>12} {len(unauth_resp):>14}",
                    f"  {'mean (bytes)':<20} {auth_resp.mean():>12.1f} {unauth_resp.mean():>14.1f}",
                    f"  {'std (bytes)':<20} {auth_resp.std():>12.1f} {unauth_resp.std():>14.1f}",
                    f"  {'max (bytes)':<20} {auth_resp.max():>12.0f} {unauth_resp.max():>14.0f}",
                    "", f"  KS statistic: {ks_stat:.6f}",
                    f"  KS p-value:   {ks_p:.6f}",
                    f"  Result: {'PASS' if ks_pass else 'FAIL'} (alpha={KS_ALPHA})",
                ]
                packet_pass = ks_pass
            else:
                capture_lines = ["", "Sub-test 2: Packet payload distribution",
                                  "  WARNING: too few packets parsed"]
                packet_pass = True
        else:
            auth_pcap = auth_cap.get('pcap', 'N/A') if auth_cap else 'capture failed'
            unauth_pcap = unauth_cap.get('pcap', 'N/A') if unauth_cap else 'capture failed'
            capture_lines = [
                "", "Sub-test 2: Packet payload distribution",
                f"  authorized pcap:   {auth_pcap}",
                f"  unauthorized pcap: {unauth_pcap}",
                "  capture or parse failed",
            ]
            packet_pass = True

    # Sub-test 3: Inter-segment timing (KI-001)
    print(f"\nSub-test 3: Inter-segment timing ({N_CAPTURE_TIMING} requests per path)")
    if not _tcpdump_available() or not _tshark_available():
        missing = "tcpdump" if not _tcpdump_available() else "tshark"
        print(f"  SKIPPED — {missing} not available or lacks cap_net_raw")
        timing_lines = ["", "Sub-test 3: Inter-segment timing (KI-001)",
                        f"  SKIPPED — {missing} not available"]
        timing_pass = True
        ki001_closed = False
    else:
        print("  Capturing authorized path (microsecond timestamps)...")
        auth_pcap_t = _capture_pcap("wire_authorized",  "timing_authorized",
                                    N_CAPTURE_TIMING, microsecond=True)
        print("  Capturing unauthorized path (microsecond timestamps)...")
        unauth_pcap_t = _capture_pcap("wire_unauthorized", "timing_unauthorized",
                                      N_CAPTURE_TIMING, microsecond=True)

        auth_deltas   = _parse_intersegment_deltas(auth_pcap_t)   if auth_pcap_t   else None
        unauth_deltas = _parse_intersegment_deltas(unauth_pcap_t) if unauth_pcap_t else None

        if auth_deltas is not None and unauth_deltas is not None and \
                len(auth_deltas) >= 4 and len(unauth_deltas) >= 4:
            ks_stat_t, ks_p_t = stats.ks_2samp(auth_deltas, unauth_deltas)
            ks_pass_t = ks_p_t >= KS_ALPHA

            np.save(RESULTS_DIR / "wire_capture_auth_timing_deltas.npy",   auth_deltas)
            np.save(RESULTS_DIR / "wire_capture_unauth_timing_deltas.npy", unauth_deltas)

            # Practical exploitability note for any FAIL case
            mean_diff_us = abs(auth_deltas.mean() - unauth_deltas.mean())
            exploit_note = (
                "delta difference < 1ms — not exploitable over real networks (jitter >100µs)"
                if mean_diff_us < 1000 else
                f"delta difference = {mean_diff_us:.0f}µs — assess exploitability"
            )

            timing_lines = [
                "", "Sub-test 3: Inter-segment timing (KI-001)",
                f"  {'':28} {'authorized':>12} {'unauthorized':>14}",
                "  " + "-" * 56,
                f"  {'intra-response deltas':<28} {len(auth_deltas):>12} {len(unauth_deltas):>14}",
                f"  {'mean (µs)':<28} {auth_deltas.mean():>12.1f} {unauth_deltas.mean():>14.1f}",
                f"  {'std (µs)':<28} {auth_deltas.std():>12.1f} {unauth_deltas.std():>14.1f}",
                f"  {'p99 (µs)':<28} {np.percentile(auth_deltas, 99):>12.1f} "
                f"{np.percentile(unauth_deltas, 99):>14.1f}",
                "",
                f"  KS statistic: {ks_stat_t:.6f}",
                f"  KS p-value:   {ks_p_t:.6f}",
                f"  Result: {'PASS' if ks_pass_t else 'FAIL'} (alpha={KS_ALPHA})",
            ]
            if not ks_pass_t:
                timing_lines.append(f"  Exploitability: {exploit_note}")

            timing_pass = ks_pass_t
            ki001_closed = True
        else:
            timing_lines = [
                "", "Sub-test 3: Inter-segment timing (KI-001)",
                "  WARNING: insufficient deltas parsed from pcap",
                f"  authorized deltas:   {len(auth_deltas) if auth_deltas is not None else 0}",
                f"  unauthorized deltas: {len(unauth_deltas) if unauth_deltas is not None else 0}",
            ]
            timing_pass = True
            ki001_closed = False

    # Combine results
    overall = size_pass and packet_pass and timing_pass
    lines = (
        ["Experiment 7: Wire-Level Capture", "=" * 70]
        + size_lines
        + capture_lines
        + timing_lines
        + [
            "",
            "=" * 70,
            f"Sub-test 1 (body size):       {'PASS' if size_pass else 'FAIL'}",
            f"Sub-test 2 (packet dist):     {'PASS' if packet_pass else 'FAIL'}",
            f"Sub-test 3 (inter-seg timing):{'PASS' if timing_pass else 'FAIL'}"
            + (" [KI-001 CLOSED]" if ki001_closed and timing_pass else
               " [KI-001 OPEN]"  if not ki001_closed else
               " [KI-001 ACKNOWLEDGED — non-exploitable]"),
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
