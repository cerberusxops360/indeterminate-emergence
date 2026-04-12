"""
Experiment 4: Syscall Trace Comparison

Compare per-call syscall traces for the authorized path (simulate_tool) vs
the unauthorized path (dummy_computation). Uses strace -tt -T for microsecond
timestamps and per-call durations.

Run from poc/ directory:
    python -m eval.syscall_trace

Requires strace. On some systems: sudo python -m eval.syscall_trace
"""

import collections
import re
import subprocess
import sys
import textwrap
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"
N_RUNS = 5  # strace runs per path (strace is slow; 5 gives enough signal)

# Small Python snippets run under strace. sys.path.insert ensures src/ is found.
_SCRIPT_AUTHORIZED = textwrap.dedent("""\
    import asyncio, sys
    sys.path.insert(0, '.')
    from src.executor import simulate_tool
    asyncio.run(simulate_tool('web_search', {'query': 'test'}))
""")

_SCRIPT_UNAUTHORIZED = textwrap.dedent("""\
    import asyncio, sys
    sys.path.insert(0, '.')
    from src.executor import dummy_computation
    asyncio.run(dummy_computation())
""")

# strace line format: HH:MM:SS.usec syscall(args) = retval <duration>
_STRACE_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}\.\d+\s+"    # timestamp
    r"(\w+)\s*\("                       # syscall name
    r".*?\)\s*=\s*[-\d]+"              # args + return value
    r"\s+<([\d.]+)>$"                  # duration in seconds
)


def _run_strace(script: str, label: str) -> list[str]:
    """
    Run strace on a Python snippet. Returns the raw strace lines (stderr).
    Saves raw output to results/syscall_trace_{label}.txt.
    """
    out_path = RESULTS_DIR / f"syscall_trace_{label}.txt"
    cmd = [
        "strace",
        "-tt",          # absolute timestamps with microseconds
        "-T",           # time spent in each syscall
        "-e", "trace=all",
        "-o", str(out_path),
        "python3", "-c", script,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and "strace: attach" not in result.stderr:
        # Non-zero exit from the traced process itself is fine;
        # strace errors go to stdout.
        pass
    lines = out_path.read_text().splitlines() if out_path.exists() else []
    return lines


def _parse_strace(lines: list[str]) -> dict:
    """
    Parse strace -tt -T output. Returns:
      - counts: {syscall: count}
      - durations: {syscall: [duration_seconds, ...]}
      - total_time: sum of all syscall durations
    """
    counts: dict[str, int] = collections.defaultdict(int)
    durations: dict[str, list[float]] = collections.defaultdict(list)

    for line in lines:
        m = _STRACE_RE.match(line.strip())
        if not m:
            continue
        syscall = m.group(1)
        duration = float(m.group(2))
        counts[syscall] += 1
        durations[syscall].append(duration)

    total_time = sum(d for ds in durations.values() for d in ds)
    return {
        "counts": dict(counts),
        "durations": {k: v for k, v in durations.items()},
        "total_time": total_time,
    }


def _top_by_count(counts: dict[str, int], n: int = 15) -> list[tuple[str, int]]:
    return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:n]


def _top_by_time(durations: dict[str, list[float]], n: int = 15) -> list[tuple[str, float]]:
    totals = {k: sum(v) for k, v in durations.items()}
    return sorted(totals.items(), key=lambda x: x[1], reverse=True)[:n]


def run_syscall_trace() -> bool:
    RESULTS_DIR.mkdir(exist_ok=True)

    # Check strace is available
    probe = subprocess.run(["strace", "--version"], capture_output=True)
    if probe.returncode != 0:
        print("ERROR: strace not found. Install with: sudo apt install strace")
        return False

    print("Experiment 4: Syscall Trace Comparison")
    print("=" * 70)
    print(f"Runs per path: {N_RUNS}")

    all_auth: list[str] = []
    all_unauth: list[str] = []

    for i in range(N_RUNS):
        print(f"  Run {i+1}/{N_RUNS}...", end=" ", flush=True)
        auth_lines = _run_strace(_SCRIPT_AUTHORIZED, f"authorized_run{i+1}")
        unauth_lines = _run_strace(_SCRIPT_UNAUTHORIZED, f"unauthorized_run{i+1}")
        all_auth.extend(auth_lines)
        all_unauth.extend(unauth_lines)
        print("done")

    auth = _parse_strace(all_auth)
    unauth = _parse_strace(all_unauth)

    # Syscalls present in one path but not the other
    auth_only = set(auth["counts"]) - set(unauth["counts"])
    unauth_only = set(unauth["counts"]) - set(auth["counts"])
    shared = set(auth["counts"]) & set(unauth["counts"])

    lines = [
        "Experiment 4: Syscall Trace Comparison",
        "=" * 70,
        f"Runs per path: {N_RUNS}",
        "",
        f"Total syscall events — authorized: {sum(auth['counts'].values())}  "
        f"unauthorized: {sum(unauth['counts'].values())}",
        f"Total syscall time  — authorized: {auth['total_time']*1000:.2f}ms  "
        f"unauthorized: {unauth['total_time']*1000:.2f}ms",
        "",
        "Syscalls present in AUTHORIZED only:",
        "  " + (", ".join(sorted(auth_only)) if auth_only else "(none)"),
        "",
        "Syscalls present in UNAUTHORIZED only:",
        "  " + (", ".join(sorted(unauth_only)) if unauth_only else "(none)"),
        "",
        "Top 15 syscalls by count:",
        f"  {'syscall':<20} {'authorized':>12} {'unauthorized':>14}",
        "  " + "-" * 48,
    ]

    all_syscalls = sorted(set(auth["counts"]) | set(unauth["counts"]),
                          key=lambda s: auth["counts"].get(s, 0) + unauth["counts"].get(s, 0),
                          reverse=True)[:15]
    for sc in all_syscalls:
        a = auth["counts"].get(sc, 0)
        u = unauth["counts"].get(sc, 0)
        lines.append(f"  {sc:<20} {a:>12} {u:>14}")

    lines += [
        "",
        "Top 10 syscalls by total time:",
        f"  {'syscall':<20} {'authorized (ms)':>16} {'unauthorized (ms)':>18}",
        "  " + "-" * 56,
    ]

    all_by_time = sorted(
        set(auth["durations"]) | set(unauth["durations"]),
        key=lambda s: sum(auth["durations"].get(s, [])) + sum(unauth["durations"].get(s, [])),
        reverse=True,
    )[:10]
    for sc in all_by_time:
        a_ms = sum(auth["durations"].get(sc, [])) * 1000
        u_ms = sum(unauth["durations"].get(sc, [])) * 1000
        lines.append(f"  {sc:<20} {a_ms:>16.3f} {u_ms:>18.3f}")

    distinguishable = bool(auth_only or unauth_only)
    lines += [
        "",
        "=" * 70,
        f"Path-exclusive syscalls detected: {distinguishable}",
        f"Assessment: {'DISTINGUISHABLE' if distinguishable else 'INDISTINGUISHABLE'} "
        f"at syscall-type level",
    ]

    summary = "\n".join(lines)
    print()
    print(summary)

    summary_path = RESULTS_DIR / "syscall_trace_summary.txt"
    summary_path.write_text(summary + "\n")
    print(f"\nRaw traces: {RESULTS_DIR}/syscall_trace_*.txt")
    print(f"Summary:    {summary_path}")

    return not distinguishable


if __name__ == "__main__":
    success = run_syscall_trace()
    sys.exit(0 if success else 1)
