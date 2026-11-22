#!/usr/bin/env python3
"""Stronger statistical adversaries against the IE PoC, in process.

Six attackers (two probe-level, four session-level, including one that contrasts a session's target-tool
latencies with its own control-tool latencies) are run on REAL (authorized against unauthorized) and NEG
(authorized against authorized) collections, with a 3 ms positive control. A (tool, model) is flagged as a
leak when the Bonferroni-level bootstrap interval of AUC(REAL) - AUC(NEG) lies entirely above zero.

Usage (from poc/):  python -m eval.adversary_battery results/adversary_battery.json [sessions per class] [tool ...]
"""
import asyncio, json, sys, time
import numpy as np, httpx
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupKFold, StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier
from src.config import SessionConfig, ALL_TOOLS
from src.proxy import app, session_store, accountants
OUT = sys.argv[1] if len(sys.argv) > 1 else "results/adversary_battery.json"; N = int(sys.argv[2]) if len(sys.argv) > 2 else 400
TOOLS = sys.argv[3:] or list(ALL_TOOLS)
SEED = 20261122; CONC = int(__import__("os").environ.get("IE_BATTERY_CONC", "80")); NT = 24; NC = 12; N_BOOT = 2000; ALPHA = 0.05 / (6 * len(TOOLS))
ORDER = [("t" if i % 3 else "c") for i in range(NT + NC)]            # c t t c t t ... : 12 control, 24 target
rng = np.random.default_rng(SEED)

async def collect(tool, mode):
    specs = []
    for i in range(N):
        a = "b_%s_%s_a_%d" % (tool, mode, i); session_store.register(SessionConfig(a, [tool], 1e12, 0.0, 0.0)); specs.append((a, 1))
        b = "b_%s_%s_b_%d" % (tool, mode, i); session_store.register(SessionConfig(b, [] if mode == "real" else [tool], 1e12, 0.0, 0.0)); specs.append((b, 0))
    lat = np.zeros((len(specs), NT + NC)); size = np.zeros((len(specs), NT + NC)); sem = asyncio.Semaphore(CONC)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://asgi", timeout=60) as c:
        async def session(si):
            for k, kind in enumerate(ORDER):                           # probes of one session are sequential, as a real prober's would be
                async with sem:
                    t0 = time.perf_counter()
                    r = await c.post("/action", json={"tool": tool if kind == "t" else "no_such_tool", "params": {"q": "p", "record": "probe record"}, "session_id": specs[si][0]})
                    lat[si, k] = time.perf_counter() - t0; size[si, k] = len(r.content)
        await asyncio.gather(*[session(i) for i in range(len(specs))])
    return np.array([s[1] for s in specs]), lat, size

TI = [i for i, k in enumerate(ORDER) if k == "t"]; CI = [i for i, k in enumerate(ORDER) if k == "c"]
def summ(x):
    q = np.percentile(x, [25, 50, 75], axis=1).T
    ac = np.array([np.corrcoef(r[:-1], r[1:])[0, 1] if r.std() > 0 else 0.0 for r in x])
    return np.column_stack([x.mean(1), x.std(1), x.min(1), x.max(1), q, ac])
def f_seq(lat): t = lat[:, TI]; return np.column_stack([t, np.sort(t, 1), summ(t)])
def f_sum(lat): return summ(lat[:, TI])
def f_con(lat):
    t, c = lat[:, TI], lat[:, CI]
    return np.column_stack([t.mean(1) - c.mean(1), np.median(t, 1) - np.median(c, 1), t.std(1) - c.std(1), t.min(1) - c.min(1), t.max(1) - c.max(1), t[:, ::2] - c])
xgb = lambda: XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.1, subsample=0.9, random_state=7, n_jobs=8, verbosity=0)
MODELS = {
 "M1_rf_probe": ("probe", lambda: RandomForestClassifier(n_estimators=300, random_state=7, n_jobs=-1), None),
 "M2_xgb_probe": ("probe", xgb, None),
 "M3_xgb_sequence": ("session", xgb, f_seq),
 "M4_mlp_sequence": ("session", lambda: make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(64, 64), max_iter=500, random_state=7)), f_seq),
 "M5_logit_summary": ("session", lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)), f_sum),
 "M6_xgb_contrast": ("session", xgb, f_con),
}
def oof(name, y, lat, size):
    """Out-of-fold scores, one per session (probe-level scores are averaged within the session)."""
    level, mk, fx = MODELS[name]; ns = len(y)
    if level == "probe":
        X = np.column_stack([lat[:, TI].ravel(), size[:, TI].ravel()]); yy = np.repeat(y, NT); g = np.repeat(np.arange(ns), NT)
        p = cross_val_predict(mk(), X, yy, cv=GroupKFold(5), groups=g, method="predict_proba")[:, 1]
        return p.reshape(ns, NT).mean(1), p, yy
    p = cross_val_predict(mk(), fx(lat), y, cv=StratifiedKFold(5, shuffle=True, random_state=7), method="predict_proba")[:, 1]
    return p, None, None
def boot(y, p):
    n = len(y); v = np.empty(N_BOOT)
    for b in range(N_BOOT):
        i = rng.integers(0, n, n)
        v[b] = roc_auc_score(y[i], p[i]) if 0 < y[i].sum() < n else 0.5
    return v

async def main():
    R = {"n_sessions_per_class": N, "alpha": ALPHA, "cells": [], "power": {}}; t0 = time.time()
    for tool in TOOLS:
        accountants.clear(); yr, lr, sr = await collect(tool, "real")
        accountants.clear(); yn, ln, sn = await collect(tool, "neg")
        lp = ln.copy(); lp[np.ix_(yn == 1, TI)] += 0.003
        detected = []
        for name in MODELS:
            res = {}
            for lab, (y, lat, size) in {"real": (yr, lr, sr), "neg": (yn, ln, sn), "pos": (yn, lp, sn)}.items():
                p, pp, yy = oof(name, y, lat, size)
                res[lab] = (float(roc_auc_score(y, p)), boot(y, p), None if pp is None else float(roc_auc_score(yy, pp)))
            lo, hi = 100 * ALPHA / 2, 100 * (1 - ALPHA / 2)
            d = res["real"][1] - res["neg"][1]; dp = res["pos"][1] - res["neg"][1]
            cell = {"tool": tool, "model": name, "auc_real": round(res["real"][0], 4), "auc_neg": round(res["neg"][0], 4), "auc_pos": round(res["pos"][0], 4),
                    "probe_auc_real": res["real"][2], "probe_auc_neg": res["neg"][2],
                    "diff": round(res["real"][0] - res["neg"][0], 4), "diff_ci": [round(float(np.percentile(d, lo)), 4), round(float(np.percentile(d, hi)), 4)],
                    "leak_flag": bool(np.percentile(d, lo) > 0), "pos_detected": bool(np.percentile(dp, lo) > 0),
                    "advantage_real_pct": round(200 * (res["real"][0] - 0.5), 2), "advantage_neg_pct": round(200 * (res["neg"][0] - 0.5), 2), "advantage_pos_pct": round(200 * (res["pos"][0] - 0.5), 2)}
            if cell["pos_detected"]: detected.append(name)
            R["cells"].append(cell); print(json.dumps(cell), flush=True)
        R["power"][tool] = detected
    R["leaks"] = [(c["tool"], c["model"]) for c in R["cells"] if c["leak_flag"]]
    R["tools_without_power"] = [t for t, d in R["power"].items() if not d]
    R["verdict"] = "PASS" if not R["leaks"] and not R["tools_without_power"] else ("LEAK" if R["leaks"] else "NO_POWER_ON_SOME_TOOLS")
    R["seconds"] = round(time.time() - t0, 1); json.dump(R, open(OUT, "w"), indent=1)
    print("VERDICT", R["verdict"], "leaks", R["leaks"], "power", R["power"], "seconds", R["seconds"])

if __name__ == "__main__":
    asyncio.run(main())
