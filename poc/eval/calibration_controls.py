import asyncio
import time
import numpy as np
import httpx
from src.config import ALL_TOOLS, SessionConfig
from src.proxy import app, session_store, accountants
import eval.classifier_attack as ca
from eval.classifier_attack import _probe_features, _eval_level, N_PROBES

ca.N_PERM = 40
ca.N_BOOT = 300
N_SESS = 200
CONC = 48
BIAS_S = 0.003
rng = np.random.default_rng(0)

async def collect(tool, mode):
    specs = []
    for i in range(N_SESS):
        a = f"cal_{tool}_a_{i}"
        session_store.register(SessionConfig(session_id=a, authorized_tools=[tool], budget=1e12, per_query_epsilon=0.0, absorption_margin=0.0))
        specs.append((a, 1))
        if mode == "real":
            b = f"cal_{tool}_u_{i}"
            session_store.register(SessionConfig(session_id=b, authorized_tools=[], budget=1e12, per_query_epsilon=0.0, absorption_margin=0.0))
        else:
            b = f"cal_{tool}_b_{i}"
            session_store.register(SessionConfig(session_id=b, authorized_tools=[tool], budget=1e12, per_query_epsilon=0.0, absorption_margin=0.0))
        specs.append((b, 0))
    jobs = []
    for p in range(N_PROBES):
        for idx in range(len(specs)):
            jobs.append((idx, specs[idx][1], specs[idx][0]))
    rng.shuffle(jobs)
    out = [None] * len(jobs)
    sem = asyncio.Semaphore(CONC)
    tr = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=tr, base_url="http://asgi") as c:
        async def one(j, idx, label, sid):
            async with sem:
                t0 = time.perf_counter()
                r = await c.post("/action", json={"tool": tool, "params": {"query": "probe"}, "session_id": sid})
                out[j] = (idx, label, time.perf_counter() - t0, len(r.content))
        await asyncio.gather(*[one(j, jb[0], jb[1], jb[2]) for j, jb in enumerate(jobs)])
    return np.array([(o[0], o[1], o[2], o[3]) for o in out], dtype=float)

async def main():
    tools = ["web_search", "file_read"]
    lines = []
    def out(s=""):
        print(s)
        lines.append(s)
    out("Calibration controls (in-process harness, probe level)")
    out("=" * 70)
    out(f"N_SESS={N_SESS}/class, N_PROBES={N_PROBES}, N_PERM={ca.N_PERM}, N_BOOT={ca.N_BOOT}, bias={BIAS_S*1000}ms")
    out("")
    for tool in tools:
        accountants.clear()
        real = await collect(tool, "real")
        accountants.clear()
        neg = await collect(tool, "neg")
        pos = neg.copy()
        mask = pos[:, 1] == 1
        pos[mask, 2] = pos[mask, 2] + BIAS_S
        for name, arr in (("REAL auth-vs-unauth", real), ("NEG  auth-vs-auth  ", neg), ("POS  +bias on cls1 ", pos)):
            Xp, yp = _probe_features(arr)
            r = _eval_level(name, Xp, yp, "probe")
            adv = r["best_advantage"] * 100
            best = r["best"]
            pp = r["perm_p"]
            mde = r["mde_adv"] * 100
            n = r["n"]
            out(f"  {tool:11} {name} n={n} best={best:12} adv={adv:.2f}pct perm_p={pp} MDE={mde:.2f}pct")
        out("")
    out("Read: REAL advantage at or below NEG floor means indistinguishable within precision.")
    out("POS must show a clear jump with low perm_p, confirming the battery detects a real effect.")
    txt = chr(10).join(lines) + chr(10)
    f = open("results/calibration_controls.txt", "w")
    f.write(txt)
    f.close()

if __name__ == "__main__":
    asyncio.run(main())
