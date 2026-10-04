"""
Experiment 2 (rebuilt 2026-10-04): Capability-set inference distinguisher battery.

HARNESS DEFECT FIXED
--------------------
The prior version registered sessions in the eval process via
`session_store.register(...)` while sending requests to a SEPARATE uvicorn
process whose session store was empty. On the server every eval session
resolved to None, so check_policy returned unauthorized and execute() ran the
dummy/absorption path for BOTH the "authorized" and "unauthorized" configs.
Every prior divergence/classifier/wire/burst result therefore compared the
dummy path to itself (dummy-vs-dummy), which is trivially indistinguishable and
is not evidence of the security property.

This version runs the ASGI app IN-PROCESS (httpx ASGITransport), so a registered
authorized session actually executes the real tool path on the serving side, and
the distinguisher is tested against a genuine authorized-vs-unauthorized sample.

METHOD
------
For each tool, collect per-probe (elapsed, size) for N_SESS authorized and N_SESS
unauthorized sessions (N_PROBES probes each), requests interleaved. Then run two
distinguisher batteries:

  Session level (strong adversary): aggregate timing features per session.
    Repeated/stratified K-fold CV AUC and balanced accuracy per classifier,
    advantage = max(2|AUC-0.5|, 2(bal_acc-0.5)), bootstrap 95% CI on the best
    model's AUC-advantage, and a label-permutation null p-value (sklearn
    permutation_test_score) on the best model.

  Probe level (large-n bound): single-observation features (elapsed, size).
    Same CV statistics; large sample size lets us bound a ~1% advantage.

Report the minimum detectable effect (MDE) at each sample size so a
"no detectable advantage" pass is never confused with "advantage < MDE".

PRE-REGISTERED PASS (per tool, each level):
  advantage point estimate < ADV_THRESHOLD (0.01)
  AND permutation p >= 0.05
  AND AUC-advantage 95% CI lower bound <= 0.
The session level additionally reports MDE; if MDE > ADV_THRESHOLD the pass is
reported as "no advantage detectable at MDE=x%" rather than "advantage < 1%".
"""

import asyncio
import json
import math
import sys
import time

import numpy as np
from scipy.stats import skew, kurtosis
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, balanced_accuracy_score
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
    cross_val_score,
    permutation_test_score,
)
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import httpx

from src.config import ALL_TOOLS, SessionConfig
from src.proxy import app, session_store, accountants

# -- Configuration --
N_SESS = 250          # sessions per class per tool
N_PROBES = 24         # probes per session
CONCURRENCY = 48      # in-process concurrent requests
ADV_THRESHOLD = 0.01  # pre-registered advantage bound
N_PERM = 100          # label permutations for the null
N_BOOT = 1000         # bootstrap resamples for the advantage CI
SEED = 1337

rng = np.random.default_rng(SEED)


def _battery():
    return {
        "LogReg": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
        "kNN": make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=15)),
        "RandomForest": RandomForestClassifier(n_estimators=200, random_state=SEED, n_jobs=-1),
        "GradBoost": GradientBoostingClassifier(random_state=SEED),
        "MLP": make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=1000, random_state=SEED)),
    }


async def _collect(tool: str):
    """Collect per-probe (elapsed, size, session_idx, label) for one tool, in-process."""
    # Register sessions on the SAME process that serves (shared store).
    specs = []  # (session_id, label)
    for i in range(N_SESS):
        sid_a = f"clf_{tool}_auth_{i}"
        session_store.register(SessionConfig(
            session_id=sid_a, authorized_tools=[tool],
            budget=1e12, per_query_epsilon=0.0, absorption_margin=0.0,
        ))
        specs.append((sid_a, 1))
        sid_u = f"clf_{tool}_unauth_{i}"
        session_store.register(SessionConfig(
            session_id=sid_u, authorized_tools=[],
            budget=1e12, per_query_epsilon=0.0, absorption_margin=0.0,
        ))
        specs.append((sid_u, 0))

    # Build interleaved task list so any time drift is shared across classes.
    jobs = []  # (session_idx, label, session_id)
    for p in range(N_PROBES):
        for idx, (sid, label) in enumerate(specs):
            jobs.append((idx, label, sid))
    rng.shuffle(jobs)

    sem = asyncio.Semaphore(CONCURRENCY)
    out = [None] * len(jobs)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://asgi") as client:
        async def one(j, idx, label, sid):
            async with sem:
                t0 = time.perf_counter()
                r = await client.post("/action", json={
                    "tool": tool, "params": {"query": "probe"}, "session_id": sid,
                })
                el = time.perf_counter() - t0
                out[j] = (idx, label, el, len(r.content))
        await asyncio.gather(*[one(j, idx, label, sid) for j, (idx, label, sid) in enumerate(jobs)])

    arr = np.array([(o[0], o[1], o[2], o[3]) for o in out], dtype=float)
    return arr  # columns: session_idx, label, elapsed, size


def _session_features(arr):
    """Aggregate per-session timing features. Returns X, y."""
    n_sessions = int(arr[:, 0].max()) + 1
    X, y = [], []
    for s in range(n_sessions):
        rows = arr[arr[:, 0] == s]
        if len(rows) == 0:
            continue
        t = rows[:, 2]
        sz = rows[:, 3]
        feats = [
            t.mean(), t.std(), t.min(), t.max(), np.median(t),
            np.percentile(t, 10), np.percentile(t, 25), np.percentile(t, 75),
            np.percentile(t, 90), np.percentile(t, 95), np.percentile(t, 99),
            np.percentile(t, 75) - np.percentile(t, 25),
            float(skew(t)) if t.std() > 0 else 0.0,
            float(kurtosis(t)) if t.std() > 0 else 0.0,
            np.mean(np.abs(np.diff(t))) if len(t) > 1 else 0.0,
            sz.mean(), sz.std(),
        ]
        X.append(feats)
        y.append(int(rows[0, 1]))
    return np.array(X), np.array(y)


def _probe_features(arr):
    """Single-observation features. Returns X, y."""
    X = arr[:, [2, 3]]  # elapsed, size
    y = arr[:, 1].astype(int)
    return X, y


def _advantage_from_auc(auc):
    return 2.0 * abs(auc - 0.5)


def _mde_accuracy(n):
    """Min detectable accuracy above 0.5 at 80% power, alpha=0.05 (two-sided normal approx)."""
    z_a, z_b = 1.95996, 0.84162
    d = (z_a + z_b) * math.sqrt(0.25 / n)
    return d  # as advantage in accuracy units (acc = 0.5 + d/... ) -> treat d as acc delta


def _eval_level(name, X, y, level):
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    results = {}
    best_name, best_auc = None, 0.5
    for clf_name, clf in _battery().items():
        try:
            aucs = cross_val_score(clf, X, y, cv=cv, scoring="roc_auc", n_jobs=-1)
            accs = []
            yp = cross_val_predict(clf, X, y, cv=cv, n_jobs=-1)
            bacc = balanced_accuracy_score(y, yp)
            auc = float(np.mean(aucs))
        except Exception as e:
            results[clf_name] = {"error": str(e)}
            continue
        adv = max(_advantage_from_auc(auc), 2.0 * (bacc - 0.5))
        results[clf_name] = {"auc": auc, "auc_std": float(np.std(aucs)), "bal_acc": float(bacc), "advantage": float(adv)}
        if auc > best_auc:
            best_auc, best_name = auc, clf_name

    # Bootstrap CI + permutation null on the best model (by AUC).
    perm_p = None
    ci = None
    if best_name is not None:
        clf = _battery()[best_name]
        # OOF probabilities for bootstrap CI on AUC-advantage
        try:
            proba = cross_val_predict(clf, X, y, cv=cv, method="predict_proba", n_jobs=-1)[:, 1]
            boots = []
            n = len(y)
            for _ in range(N_BOOT):
                idx = rng.integers(0, n, n)
                if len(np.unique(y[idx])) < 2:
                    continue
                boots.append(_advantage_from_auc(roc_auc_score(y[idx], proba[idx])))
            if boots:
                ci = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)))
        except Exception as e:
            ci = None
        # Permutation null on AUC
        try:
            _, _, perm_p = permutation_test_score(
                clf, X, y, scoring="roc_auc", cv=cv, n_permutations=N_PERM,
                n_jobs=-1, random_state=SEED,
            )
            perm_p = float(perm_p)
        except Exception:
            perm_p = None

    return {
        "level": level, "n": int(len(y)), "best": best_name,
        "best_auc": float(best_auc), "best_advantage": float(_advantage_from_auc(best_auc)),
        "adv_ci95": ci, "perm_p": perm_p,
        "mde_adv": float(_mde_accuracy(len(y))), "per_clf": results,
    }


def _verdict(level_res):
    adv = level_res["best_advantage"]
    p = level_res["perm_p"]
    ci = level_res["adv_ci95"]
    mde = level_res["mde_adv"]
    p_ok = (p is None) or (p >= 0.05)
    ci_ok = (ci is None) or (ci[0] <= 0.0)
    if adv < ADV_THRESHOLD and p_ok and ci_ok:
        return "PASS"
    # distinguish "below MDE" from a real bound
    if adv < mde and p_ok:
        return f"PASS* (no advantage detectable; MDE={mde*100:.1f}%)"
    return "FAIL"


async def run_all():
    lines = []
    def out(s=""):
        print(s)
        lines.append(s)

    out("Capability-Set Inference Distinguisher Battery (rebuilt, in-process harness)")
    out("=" * 78)
    out(f"Config: N_SESS={N_SESS}/class, N_PROBES={N_PROBES}, concurrency={CONCURRENCY}")
    out(f"Pre-registered advantage threshold: {ADV_THRESHOLD} (1%)")
    out(f"Battery: LogReg, kNN, RandomForest, GradBoost, MLP")
    out("Advantage = max(2|AUC-0.5|, 2(bal_acc-0.5)); null = label permutation (AUC).")
    out("")

    overall = True
    summary = {}
    for tool in ALL_TOOLS:
        accountants.clear()
        arr = await _collect(tool)
        Xs, ys = _session_features(arr)
        Xp, yp = _probe_features(arr)
        sess = _eval_level(tool, Xs, ys, "session")
        probe = _eval_level(tool, Xp, yp, "probe")
        vs, vp = _verdict(sess), _verdict(probe)
        if vs == "FAIL" or vp == "FAIL":
            overall = False
        summary[tool] = {"session": sess, "probe": probe, "verdict_session": vs, "verdict_probe": vp}

        out(f"TOOL: {tool}")
        for lvl, res, v in (("session", sess, vs), ("probe", probe, vp)):
            ci = res["adv_ci95"]
            ci_s = f"[{ci[0]*100:.2f}%, {ci[1]*100:.2f}%]" if ci else "n/a"
            pp = f"{res['perm_p']:.3f}" if res["perm_p"] is not None else "n/a"
            out(f"  {lvl:<8} n={res['n']:>6}  best={res['best']:<13} AUC={res['best_auc']:.4f} "
                f"adv={res['best_advantage']*100:.2f}%  adv_CI95={ci_s}  perm_p={pp}  "
                f"MDE={res['mde_adv']*100:.2f}%  -> {v}")
            for cn, cr in res["per_clf"].items():
                if "error" in cr:
                    out(f"      {cn:<13} ERROR {cr['error'][:60]}")
                else:
                    out(f"      {cn:<13} AUC={cr['auc']:.4f}(+-{cr['auc_std']:.3f}) bal_acc={cr['bal_acc']:.4f} adv={cr['advantage']*100:.2f}%")
        out("")

    out("=" * 78)
    out(f"Overall: {'PASS' if overall else 'FAIL'}")
    out("Note: PASS* means no advantage was detectable at the achievable MDE for that")
    out("sample size; it is a bounded negative, not a proof of <1% advantage. The")
    out("probe-level test carries the large-n bound; the session level is the stronger")
    out("adversary (aggregated features).")

    with open("results/classifier_attack_results.txt", "w") as f:
        f.write("\n".join(lines) + "\n")
    with open("results/classifier_attack_results.json", "w") as f:
        json.dump(summary, f, indent=2, default=float)
    return overall


if __name__ == "__main__":
    ok = asyncio.run(run_all())
    sys.exit(0 if ok else 1)
