import asyncio
import sys
import time
import numpy as np
import httpx
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score
from src.config import SessionConfig
from src.proxy import app, session_store, accountants
from eval.classifier_attack import _probe_features

TOOL = sys.argv[1] if len(sys.argv) > 1 else "web_search"
N_SESS = int(sys.argv[2]) if len(sys.argv) > 2 else 1600
N_PROBES = 24
CONC = 80
BIAS_S = 0.003
N_BOOT = 2000
SEED = 7
rng = np.random.default_rng(SEED)

def make_model():
    return RandomForestClassifier(n_estimators=300, random_state=SEED, n_jobs=-1)

async def collect(mode):
    specs = []
    for i in range(N_SESS):
        a = f"hg_{mode}_a_{i}"
        session_store.register(SessionConfig(session_id=a, authorized_tools=[TOOL], budget=1e12, per_query_epsilon=0.0, absorption_margin=0.0))
        specs.append((a, 1))
        if mode == "real":
            b = f"hg_{mode}_u_{i}"
            session_store.register(SessionConfig(session_id=b, authorized_tools=[], budget=1e12, per_query_epsilon=0.0, absorption_margin=0.0))
        else:
            b = f"hg_{mode}_b_{i}"
            session_store.register(SessionConfig(session_id=b, authorized_tools=[TOOL], budget=1e12, per_query_epsilon=0.0, absorption_margin=0.0))
        specs.append((b, 0))
    jobs = []
    for p in range(N_PROBES):
        for idx in range(len(specs)):
            jobs.append((specs[idx][1], specs[idx][0]))
    out = [None] * len(jobs)
    sem = asyncio.Semaphore(CONC)
    tr = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=tr, base_url="http://asgi") as c:
        async def one(j, label, sid):
            async with sem:
                t0 = time.perf_counter()
                r = await c.post("/action", json={"tool": TOOL, "params": {"query": "probe"}, "session_id": sid})
                out[j] = (0, label, time.perf_counter() - t0, len(r.content))
        await asyncio.gather(*[one(j, jobs[j][0], jobs[j][1]) for j in range(len(jobs))])
    return np.array(out, dtype=float)

def auc_boot(arr):
    X, y = _probe_features(arr)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    proba = cross_val_predict(make_model(), X, y, cv=cv, method="predict_proba", n_jobs=-1)[:, 1]
    auc = roc_auc_score(y, proba)
    n = len(y)
    vals = []
    for _ in range(N_BOOT):
        idx = rng.integers(0, n, n)
        if len(np.unique(y[idx])) < 2:
            continue
        vals.append(roc_auc_score(y[idx], proba[idx]))
    return auc, np.array(vals)

async def main():
    lines = []
    def out(s=""):
        print(s)
        lines.append(s)
    out(f"Hardened gate (single pre-registered RandomForest) tool={TOOL}")
    out("=" * 70)
    out(f"N_SESS={N_SESS}/class, N_PROBES={N_PROBES}, probe n per condition={N_SESS*2*N_PROBES}, N_BOOT={N_BOOT}")
    out("")
    accountants.clear()
    real = await collect("real")
    accountants.clear()
    neg = await collect("neg")
    pos = neg.copy()
    m = pos[:, 1] == 1
    pos[m, 2] = pos[m, 2] + BIAS_S
    auc_r, boot_r = auc_boot(real)
    auc_n, boot_n = auc_boot(neg)
    auc_p, boot_p = auc_boot(pos)
    def adv(a):
        return 2.0 * (a - 0.5)
    r_lo = np.percentile(boot_r, 2.5)
    r_hi = np.percentile(boot_r, 97.5)
    n_hi = np.percentile(boot_n, 97.5)
    k = min(len(boot_r), len(boot_n))
    diff = boot_r[:k] - boot_n[:k]
    d_lo = np.percentile(diff, 2.5)
    d_hi = np.percentile(diff, 97.5)
    out(f"REAL auth-vs-unauth : AUC={auc_r:.4f}  AUC95=[{r_lo:.4f},{r_hi:.4f}]  advantage={adv(auc_r)*100:.2f}pct  adv_upper95={adv(r_hi)*100:.2f}pct")
    out(f"NEG  auth-vs-auth   : AUC={auc_n:.4f}  advantage={adv(auc_n)*100:.2f}pct  adv_upper95={adv(n_hi)*100:.2f}pct  (noise floor)")
    out(f"POS  +3ms on cls1   : AUC={auc_p:.4f}  advantage={adv(auc_p)*100:.2f}pct  (power check)")
    out(f"REAL-minus-NEG AUC diff 95pct CI = [{d_lo:.4f}, {d_hi:.4f}]")
    out("")
    indistinguishable = d_lo <= 0.0
    certified = adv(r_hi) * 100.0
    pos_detected = adv(auc_p) > adv(auc_n) + 0.02
    out(f"VERDICT indistinguishable (REAL not above NEG floor): {indistinguishable}")
    out(f"CERTIFIED BOUND: capability-inference advantage <= {certified:.2f}pct at 95pct confidence (single pre-registered RF, probe n={N_SESS*2*N_PROBES})")
    out(f"Positive control detected 3ms bias: {pos_detected}")
    txt = chr(10).join(lines) + chr(10)
    f = open(f"results/hardened_gate_{TOOL}.txt", "w")
    f.write(txt)
    f.close()

if __name__ == "__main__":
    asyncio.run(main())
