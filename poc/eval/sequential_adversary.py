#!/usr/bin/env python3
"""Sequential Bayesian adversary: does belief stay bounded as probes accumulate? (pre-registered 2026-11-22)

Usage (from poc/):  python -m eval.sequential_adversary results/sequential_adversary.json
"""
import asyncio, json, sys, time
import numpy as np, httpx
from src.config import SessionConfig
from src.proxy import app, session_store, accountants
OUT = sys.argv[1] if len(sys.argv) > 1 else "results/sequential_adversary.json"
TOOL = "web_search"; N = int(sys.argv[2]) if len(sys.argv) > 2 else 400; K = 48; CONC = 80; SEED = 20261123; TAU = 0.011; BINS = 50

async def collect(tag):
    specs = []
    for i in range(N):
        a = "sq_%s_a_%d" % (tag, i); session_store.register(SessionConfig(a, [TOOL], 1e12, 0.0, 0.0)); specs.append((a, 1))
        b = "sq_%s_u_%d" % (tag, i); session_store.register(SessionConfig(b, [], 1e12, 0.0, 0.0)); specs.append((b, 0))
    lat = np.zeros((len(specs), K)); size = np.zeros((len(specs), K)); sem = asyncio.Semaphore(CONC)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://asgi", timeout=60) as c:
        async def session(si):
            for k in range(K):
                async with sem:
                    t0 = time.perf_counter()
                    r = await c.post("/action", json={"tool": TOOL, "params": {"q": "p"}, "session_id": specs[si][0]})
                    lat[si, k] = time.perf_counter() - t0; size[si, k] = len(r.content)
        await asyncio.gather(*[session(i) for i in range(len(specs))])
    return np.array([s[1] for s in specs]), lat, size

def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(float(c - h), 4), round(float(c + h), 4)]

def attack(ytr, ltr, yte, lte):
    lo, hi = np.percentile(ltr, [0.5, 99.5]); edges = np.linspace(lo, hi, BINS + 1)
    def hist(x):
        h = np.histogram(np.clip(x, lo, hi), bins=edges)[0].astype(float) + 1.0; return h / h.sum()
    p1, p0 = hist(ltr[ytr == 1].ravel()), hist(ltr[ytr == 0].ravel())
    idx = np.clip(np.digitize(np.clip(lte, lo, hi), edges) - 1, 0, BINS - 1)
    llr = np.cumsum(np.log(p1[idx]) - np.log(p0[idx]), axis=1)          # running log likelihood ratio per session
    post = 1.0 / (1.0 + np.exp(-llr))                                   # posterior P(authorized), prior 0.5
    guess = (post[:, -1] > 0.5).astype(int); correct = int((guess == yte).sum()); n = len(yte)
    return {"accuracy": round(correct / n, 4), "accuracy_ci95": wilson(correct, n),
            "mean_abs_move_from_half": [round(float(np.abs(post[:, k - 1] - 0.5).mean()), 4) for k in (1, 12, 24, 48)],
            "posterior_authorized_sessions_p05_p50_p95": [round(float(v), 4) for v in np.percentile(post[yte == 1, -1], [5, 50, 95])],
            "posterior_unauthorized_sessions_p05_p50_p95": [round(float(v), 4) for v in np.percentile(post[yte == 0, -1], [5, 50, 95])],
            "max_posterior_reached": round(float(post.max()), 4), "min_posterior_reached": round(float(post.min()), 4)}

async def main():
    t0 = time.time(); accountants.clear(); ytr, ltr, s1 = await collect("tr"); accountants.clear(); yte, lte, s2 = await collect("te")
    bound = (1 + K * TAU) / 2
    real = attack(ytr, ltr, yte, lte)
    ltr_p, lte_p = ltr.copy(), lte.copy(); ltr_p[ytr == 1] += 0.003; lte_p[yte == 1] += 0.003
    pos = attack(ytr, ltr_p, yte, lte_p)
    R = {"tool": TOOL, "sessions_per_class": N, "probes_per_session": K, "tau_assumed": TAU, "composition_bound_on_accuracy": round(bound, 4),
         "sizes_all_identical": bool(len(np.unique(np.concatenate([s1.ravel(), s2.ravel()]))) == 1), "real": real, "positive_control_3ms": pos,
         "N1_accuracy_ci_contains_half_and_below_bound": bool(real["accuracy_ci95"][0] <= 0.5 <= real["accuracy_ci95"][1] and real["accuracy_ci95"][1] < bound),
         "N3_positive_control_above_half": bool(pos["accuracy_ci95"][0] > 0.5), "seconds": round(time.time() - t0, 1)}
    json.dump(R, open(OUT, "w"), indent=1); print(json.dumps(R, indent=1))

if __name__ == "__main__":
    asyncio.run(main())
