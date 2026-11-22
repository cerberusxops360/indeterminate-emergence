#!/usr/bin/env python3
"""Red team and differential fuzz of the IE PoC proxy over real HTTP on loopback.

Every probe is sent to five session states per tool (authorized, unauthorized, authorized for the other
tools only, absorbing, no such session) and every observable is compared: status line, headers, body
length, body hash, latency. Sessions are registered in the SAME process that serves them, so the
April 2026 harness fault (client and server holding different session stores) cannot occur.

Flag rules: any difference in the set of response signatures between states; or a latency difference
by two-sample KS below 0.05 / (number of comparisons).

Usage (from poc/):  python -m eval.redteam_fuzz results/redteam_fuzz.json
"""
import asyncio, hashlib, json, sys, threading, time
import numpy as np
from scipy import stats
import uvicorn
from src.config import SessionConfig, ALL_TOOLS
from src.proxy import app, session_store, accountants
OUT = sys.argv[1] if len(sys.argv) > 1 else "results/redteam_fuzz.json"; PORT = 18474; R = 20; CONC = 40
BIG = 1e12
for t in ALL_TOOLS:
    session_store.register(SessionConfig("A_" + t, [t], BIG, 0.0, 0.0))
    session_store.register(SessionConfig("P_" + t, [x for x in ALL_TOOLS if x != t], BIG, 0.0, 0.0))
    session_store.register(SessionConfig("X_" + t, [t], 1.0, 1.0, 0.0))
session_store.register(SessionConfig("U", [], BIG, 0.0, 0.0))
session_store.register(SessionConfig("U2", [], BIG, 0.0, 0.0))
session_store.register(SessionConfig("D_victim", list(ALL_TOOLS)))            # default budget 50, eps 1, margin 5
CONFIGS = {"authorized": lambda t: "A_" + t, "unauthorized": lambda t: "U", "other_tools_only": lambda t: "P_" + t,
           "absorbing": lambda t: "X_" + t, "no_such_session": lambda t: "nosuch_" + t}
J = {"Content-Type": "application/json"}
def jb(**k): return json.dumps(k)
NORMAL = '{"tool": "{TOOL}", "params": {}, "session_id": "{SESSION}"}'
PROBES = [
 ("baseline", "POST", "/action", J, NORMAL, "normal"),
 ("params_realistic", "POST", "/action", J, '{"tool": "{TOOL}", "params": {"query": "probe", "path": "/etc/hosts", "expression": "2+2", "code": "print(1)", "record": "probe record"}, "session_id": "{SESSION}"}', "normal"),
 ("tool_crash_params", "POST", "/action", J, '{"tool": "{TOOL}", "params": {"expression": "1/0", "path": "/nonexistent/../x", "query": "SELECT 1/0", "code": "raise Exception(1)", "q": ""}, "session_id": "{SESSION}"}', "normal"),
 ("oversized_params_150k", "POST", "/action", J, '{"tool": "{TOOL}", "params": {"q": "' + "X" * 150000 + '"}, "session_id": "{SESSION}"}', "normal"),
 ("deep_nested_params", "POST", "/action", J, '{"tool": "{TOOL}", "params": ' + '{"a":' * 200 + "1" + "}" * 200 + ', "session_id": "{SESSION}"}', "normal"),
 ("params_string", "POST", "/action", J, '{"tool": "{TOOL}", "params": "notanobject", "session_id": "{SESSION}"}', "normal"),
 ("params_array", "POST", "/action", J, '{"tool": "{TOOL}", "params": [1,2,3], "session_id": "{SESSION}"}', "normal"),
 ("params_null", "POST", "/action", J, '{"tool": "{TOOL}", "params": null, "session_id": "{SESSION}"}', "normal"),
 ("missing_params", "POST", "/action", J, '{"tool": "{TOOL}", "session_id": "{SESSION}"}', "normal"),
 ("tool_as_list", "POST", "/action", J, '{"tool": ["{TOOL}"], "params": {}, "session_id": "{SESSION}"}', "normal"),
 ("tool_as_object", "POST", "/action", J, '{"tool": {"name": "{TOOL}"}, "params": {}, "session_id": "{SESSION}"}', "normal"),
 ("tool_as_number", "POST", "/action", J, '{"tool": 7, "params": {}, "session_id": "{SESSION}"}', "normal"),
 ("tool_null", "POST", "/action", J, '{"tool": null, "params": {}, "session_id": "{SESSION}"}', "normal"),
 ("unknown_tool", "POST", "/action", J, '{"tool": "__nope__", "params": {}, "session_id": "{SESSION}"}', "normal"),
 ("duplicate_tool_key", "POST", "/action", J, '{"tool": "__nope__", "tool": "{TOOL}", "params": {}, "session_id": "{SESSION}"}', "normal"),
 ("duplicate_tool_key_rev", "POST", "/action", J, '{"tool": "{TOOL}", "tool": "__nope__", "params": {}, "session_id": "{SESSION}"}', "normal"),
 ("tool_zero_width", "POST", "/action", J, '{"tool": "{TOOL}\\u200b", "params": {}, "session_id": "{SESSION}"}', "normal"),
 ("tool_upper", "POST", "/action", J, '{"tool": "{TOOL}", "TOOL": "x", "params": {}, "session_id": "{SESSION}", "extra": [1,2,{"a":null}]}', "normal"),
 ("tool_trailing_space", "POST", "/action", J, '{"tool": "{TOOL} ", "params": {}, "session_id": "{SESSION}"}', "normal"),
 ("session_as_object", "POST", "/action", J, '{"tool": "{TOOL}", "params": {}, "session_id": {"id": "{SESSION}"}}', "normal"),
 ("session_as_list", "POST", "/action", J, '{"tool": "{TOOL}", "params": {}, "session_id": ["{SESSION}"]}', "normal"),
 ("session_null", "POST", "/action", J, '{"tool": "{TOOL}", "params": {}, "session_id": null}', "normal"),
 ("body_array", "POST", "/action", J, '["{SESSION}", "{TOOL}"]', "normal"),
 ("body_scalar", "POST", "/action", J, '42', "normal"),
 ("body_string", "POST", "/action", J, '"{SESSION}"', "normal"),
 ("malformed_json", "POST", "/action", J, '{"tool": "{TOOL}", "params": {}, "session_id": "{SESSION}"', "normal"),
 ("empty_body", "POST", "/action", J, '', "normal"),
 ("empty_object", "POST", "/action", J, '{}', "normal"),
 ("wrong_content_type", "POST", "/action", {"Content-Type": "text/plain"}, NORMAL, "normal"),
 ("no_content_type", "POST", "/action", {}, NORMAL, "normal"),
 ("extra_headers", "POST", "/action", {"Content-Type": "application/json", "X-Session": "{SESSION}", "X-Tool": "{TOOL}", "Accept": "text/html", "Accept-Encoding": "gzip, br"}, NORMAL, "normal"),
 ("query_string", "POST", "/action?session_id={SESSION}&tool={TOOL}&debug=1", J, NORMAL, "normal"),
 ("get_method", "GET", "/action", J, NORMAL, "normal"),
 ("put_method", "PUT", "/action", J, NORMAL, "normal"),
 ("trailing_slash", "POST", "/action/", J, NORMAL, "normal"),
 ("wrong_path", "POST", "/actions", J, NORMAL, "normal"),
 ("docs_path", "GET", "/openapi.json", {}, "", "normal"),
 ("pipeline2", "POST", "/action", J, NORMAL, "pipeline2"),
 ("burst20", "POST", "/action", J, NORMAL, "burst20"),
 ("slow_body", "POST", "/action", J, NORMAL, "slow_body"),
]

async def send(method, path, headers, body, mode="normal"):
    """One raw HTTP exchange. Returns list of (latency, signature) for each response read."""
    b = body.encode()
    def req(close):
        h = "".join("%s: %s\r\n" % kv for kv in headers.items())
        return ("%s %s HTTP/1.1\r\nHost: t\r\n%sContent-Length: %d\r\nConnection: %s\r\n\r\n" % (method, path, h, len(b), "close" if close else "keep-alive")).encode()
    t0 = time.perf_counter()
    try:
        rd, wr = await asyncio.open_connection("127.0.0.1", PORT)
        if mode == "pipeline2": wr.write(req(False) + b + req(True) + b)
        elif mode == "slow_body":
            wr.write(req(True)); await wr.drain(); await asyncio.sleep(1.0); wr.write(b)
        else: wr.write(req(True) + b)
        await wr.drain()
        raw = await asyncio.wait_for(rd.read(-1), 20); lat = time.perf_counter() - t0
        wr.close()
    except Exception as e:
        return [(time.perf_counter() - t0, ("EXC", type(e).__name__))]
    out = []
    for part in raw.split(b"HTTP/1.1 ")[1:]:
        head, _, bod = part.partition(b"\r\n\r\n")
        lines = head.decode("latin1").split("\r\n")
        hs = tuple(sorted((l.split(":", 1)[0].lower(), l.split(":", 1)[1].strip()) for l in lines[1:] if ":" in l and not l.lower().startswith("date:")))
        out.append((lat, (lines[0], hs, len(bod), hashlib.sha256(bod).hexdigest()[:12])))
    return out or [(lat, ("EMPTY", len(raw)))]

async def fuzz():
    sem = asyncio.Semaphore(CONC); res = {}          # (probe, config) -> {"sig": Counter-ish, "lat": []}
    async def one(name, method, path, headers, body, mode, cfg, tool):
        sid = CONFIGS[cfg](tool); sub = lambda s: s.replace("{SESSION}", sid).replace("{TOOL}", tool)
        async with sem:
            if mode == "burst20":
                rs = sum(await asyncio.gather(*[send(method, sub(path), {k: sub(v) for k, v in headers.items()}, sub(body)) for _ in range(20)]), [])
            else:
                rs = await send(method, sub(path), {k: sub(v) for k, v in headers.items()}, sub(body), mode)
        d = res.setdefault((name, cfg), {"sig": {}, "lat": []})
        for lat, sig in rs:
            k = json.dumps(sig); d["sig"][k] = d["sig"].get(k, 0) + 1; d["lat"].append(lat)
    jobs = []
    for (name, method, path, headers, body, mode) in PROBES:
        reps = 2 if mode == "burst20" else R
        for tool in ALL_TOOLS:
            for cfg in CONFIGS:
                for _ in range(reps): jobs.append(one(name, method, path, headers, body, mode, cfg, tool))
    import random; random.Random(1).shuffle(jobs)
    await asyncio.gather(*jobs)
    return res

async def interference(tool):
    """Does a flood of authorized work move another session's latency differently from a flood of unauthorized work?
    Phases alternate A B B A B A A B so that drift in background load cannot pass for a difference between labels
    (a single A-then-B comparison did exactly that on 2026-11-21)."""
    out = {"flood_authorized": [], "flood_unauthorized": []}
    for label in ("flood_authorized", "flood_unauthorized", "flood_unauthorized", "flood_authorized",
                  "flood_unauthorized", "flood_authorized", "flood_authorized", "flood_unauthorized"):
        sid = "A_" + tool if label == "flood_authorized" else "U"
        stop = [False]
        async def flood():
            while not stop[0]: await send("POST", "/action", J, jb(tool=tool, params={"record": "flood"}, session_id=sid))
        fl = [asyncio.create_task(flood()) for _ in range(150)]
        await asyncio.sleep(3.0)
        lat = [(await send("POST", "/action", J, jb(tool="calculator", params={}, session_id="U2")))[0][0] for _ in range(40)]
        stop[0] = True; await asyncio.gather(*fl); await asyncio.sleep(2.0)
        out[label].append(float(np.median(lat)))
    return out


async def budget_drain():
    """White-box check of the auditor's finding: unknown-tool requests still charge the victim session's budget."""
    before = accountants.get("D_victim")
    for _ in range(60): await send("POST", "/action", J, jb(tool="not_a_real_tool", params={}, session_id="D_victim"))
    a = accountants["D_victim"]
    return {"accountant_existed_before": before is not None, "queries": a.query_count, "spent": a.spent, "threshold": round(a.threshold, 2), "absorbing_after_60_unknown_tool_calls": a.absorbing}

async def main():
    t0 = time.time(); res = await fuzz(); names = [p[0] for p in PROBES]; rep = {"probes": {}, "seconds": None}
    ntests = len(names) * (len(CONFIGS) - 1); flagged_t = []; flagged_s = []
    for n in names:
        base = res[(n, "authorized")]; e = {"responses": {c: len(res[(n, c)]["lat"]) for c in CONFIGS}, "authorized_signatures": {k[:150]: v for k, v in base["sig"].items()},
             "median_ms": {c: round(float(np.median(res[(n, c)]["lat"])) * 1e3, 1) for c in CONFIGS}, "ks_p_vs_authorized": {}, "signature_sets_equal": {}}
        for c in CONFIGS:
            if c == "authorized": continue
            e["signature_sets_equal"][c] = set(res[(n, c)]["sig"]) == set(base["sig"])
            p = float(stats.ks_2samp(base["lat"], res[(n, c)]["lat"]).pvalue); e["ks_p_vs_authorized"][c] = round(p, 5)
            if not e["signature_sets_equal"][c]: flagged_s.append((n, c))
            if p < 0.05 / ntests: flagged_t.append((n, c, p))
        rep["probes"][n] = e
    rep["tests"] = ntests; rep["bonferroni_alpha"] = 0.05 / ntests
    rep["flagged_signature_differences"] = flagged_s; rep["flagged_timing_differences"] = flagged_t
    allp = sorted(p for e in rep["probes"].values() for p in e["ks_p_vs_authorized"].values()); rep["smallest_ks_p"] = allp[:5]; rep["share_p_below_0.05"] = round(float(np.mean(np.array(allp) < 0.05)), 3)
    rep["interference"] = {}
    for tool in [t for t in ("web_search", "record_write") if t in ALL_TOOLS]:
        inter = await interference(tool); e = {k + "_phase_medians_ms": [round(v * 1e3, 1) for v in vs] for k, vs in inter.items()}
        e["mann_whitney_p"] = round(float(stats.mannwhitneyu(inter["flood_authorized"], inter["flood_unauthorized"]).pvalue), 4); rep["interference"][tool] = e
    rep["budget_drain"] = await budget_drain(); rep["seconds"] = round(time.time() - t0, 1)
    json.dump(rep, open(OUT, "w"), indent=1)
    print("probes", len(names), "tests", ntests, "seconds", rep["seconds"])
    print("SIGNATURE DIFFERENCES across configs:", flagged_s or "none")
    print("TIMING DIFFERENCES (Bonferroni):", flagged_t or "none", "| smallest p", rep["smallest_ks_p"], "| share p<0.05", rep["share_p_below_0.05"])
    print("interference", rep["interference"]); print("budget drain", rep["budget_drain"])
    for n in names:
        e = rep["probes"][n]; sigs = list(e["authorized_signatures"])
        print("%-24s n=%d med=%sms sigs=%d %s" % (n, e["responses"]["authorized"], e["median_ms"]["authorized"], len(sigs), sigs[0][:70]))

if __name__ == "__main__":
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="critical"))
    th = threading.Thread(target=srv.run, daemon=True); th.start(); time.sleep(2)
    asyncio.run(main()); srv.should_exit = True
