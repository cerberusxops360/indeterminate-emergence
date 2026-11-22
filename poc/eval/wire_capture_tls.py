#!/usr/bin/env python3
"""Wire-level capture under TLS, sessions registered in the serving process (pre-registered 2026-11-22).

Needs tcpdump and tshark usable by the current user and openssl. Usage (from poc/):
    python -m eval.wire_capture_tls results/wire_capture_tls.json
"""
import asyncio, collections, json, os, ssl, subprocess, sys, tempfile, threading, time, random
import numpy as np
from scipy import stats
import uvicorn
from src.config import SessionConfig
from src.proxy import app, session_store
OUT = sys.argv[1] if len(sys.argv) > 1 else "results/wire_capture_tls.json"
PORT = 18475; N = int(sys.argv[2]) if len(sys.argv) > 2 else 400; CONC = 8; TOOL = "web_search"
STATES = {"authorized": "w_auth", "unauthorized": "w_unauth", "absorbing": "w_abs"}
session_store.register(SessionConfig("w_auth", [TOOL], 1e12, 0.0, 0.0))
session_store.register(SessionConfig("w_unauth", [], 1e12, 0.0, 0.0))
session_store.register(SessionConfig("w_abs", [TOOL], 1.0, 1.0, 0.0))

async def one(ctx, sid, ports, state):
    rd, wr = await asyncio.open_connection("127.0.0.1", PORT, ssl=ctx)
    ports[wr.get_extra_info("sockname")[1]] = state
    body = json.dumps({"tool": TOOL, "params": {"q": "p"}, "session_id": sid}).encode()
    wr.write(b"POST /action HTTP/1.1\r\nHost: t\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
    await wr.drain(); await rd.read(-1); wr.close()
    try: await wr.wait_closed()
    except Exception: pass

async def drive(ports):
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    jobs = [s for s in STATES for _ in range(N)]; random.Random(11).shuffle(jobs); sem = asyncio.Semaphore(CONC)
    async def run(state):
        async with sem: await one(ctx, STATES[state], ports, state)
    await asyncio.gather(*[run(s) for s in jobs])

def main():
    d = tempfile.mkdtemp(); key, crt, pcap = (os.path.join(d, n) for n in ("k.pem", "c.pem", "cap.pcap"))
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", crt, "-days", "1", "-subj", "/CN=localhost"], check=True, capture_output=True)
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="critical", ssl_keyfile=key, ssl_certfile=crt))
    threading.Thread(target=srv.run, daemon=True).start(); time.sleep(2)
    cap = subprocess.Popen(["tcpdump", "-i", "lo", "-w", pcap, "-U", "tcp", "port", str(PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1.5)
    ports = {}; t0 = time.time(); asyncio.run(drive(ports)); time.sleep(1.5); cap.terminate(); cap.wait(); srv.should_exit = True
    rows = subprocess.run(["tshark", "-r", pcap, "-T", "fields", "-e", "frame.time_epoch", "-e", "tcp.srcport", "-e", "tcp.dstport", "-e", "tcp.len"], capture_output=True, text=True).stdout.splitlines()
    conn = collections.defaultdict(list)                                  # client port -> [(time, server-to-client payload length)]
    for r in rows:
        f = r.split("\t")
        if len(f) == 4 and f[1] == str(PORT) and int(f[3] or 0) > 0: conn[int(f[2])].append((float(f[0]), int(f[3])))
    per = {s: {"total": [], "nseg": [], "seq": [], "span": []} for s in STATES}
    for port, state in ports.items():
        segs = sorted(conn.get(port, []))
        if not segs: continue
        # the response is the data after the handshake; all server-to-client payload is used, handshake included, for every state alike
        p = per[state]; p["total"].append(sum(l for _, l in segs)); p["nseg"].append(len(segs)); p["seq"].append(",".join(str(l) for _, l in segs)); p["span"].append(segs[-1][0] - segs[0][0])
    R = {"connections_per_state": {s: len(per[s]["total"]) for s in STATES}, "seconds": round(time.time() - t0, 1),
         "total_bytes_distinct_values": {s: sorted(set(per[s]["total"])) for s in STATES}, "segments_median": {s: float(np.median(per[s]["nseg"])) for s in STATES},
         "span_ms_median": {s: round(float(np.median(per[s]["span"])) * 1e3, 2) for s in STATES}, "top_sequences": {s: collections.Counter(per[s]["seq"]).most_common(3) for s in STATES}, "tests": {}}
    allv = set(v for s in STATES for v in per[s]["total"]); R["W1_total_bytes_identical"] = len(allv) == 1
    ok2 = ok3 = True
    for s in ("unauthorized", "absorbing"):
        keys = sorted(set(per["authorized"]["seq"]) | set(per[s]["seq"])); ca, cb = collections.Counter(per["authorized"]["seq"]), collections.Counter(per[s]["seq"])
        table = np.array([[ca[k] for k in keys], [cb[k] for k in keys]])
        p2 = 1.0 if len(keys) == 1 else float(stats.chi2_contingency(table + 0.5)[1])
        p3 = float(stats.ks_2samp(per["authorized"]["span"], per[s]["span"]).pvalue)
        R["tests"][s] = {"distinct_sequences": len(keys), "same_sequence_set": set(per["authorized"]["seq"]) == set(per[s]["seq"]), "chi2_p": round(p2, 4), "span_ks_p": round(p3, 4)}
        ok2 &= (p2 >= 0.05 / 4) and R["tests"][s]["same_sequence_set"]; ok3 &= p3 >= 0.05 / 4
    R["W2_sequences_do_not_differ"] = bool(ok2); R["W3_span_does_not_differ"] = bool(ok3)
    json.dump(R, open(OUT, "w"), indent=1); print(json.dumps(R, indent=1))
    for f in (key, crt, pcap): os.remove(f)
    os.rmdir(d)

if __name__ == "__main__":
    main()
