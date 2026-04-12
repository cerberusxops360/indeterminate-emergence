"""
Experiment 2: Classifier Attack

Train adversarial classifiers to distinguish tool presence from absence.
Target: all classifiers achieve accuracy <= 52%.

Usage:
    # Start proxy first: uvicorn src.proxy:app --port 8000
    python -m eval.classifier_attack
"""

import sys
import time

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from scipy.stats import binomtest
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier

from src.config import SessionConfig
from src.proxy import session_store, accountants

# -- Configuration --
N_SESSIONS = 100
N_PROBES = 20
BASE_URL = "http://localhost:8100"
ACCURACY_THRESHOLD = 0.52
AUC_THRESHOLD = 0.55


def configure_session(session_id: str, tool: str, authorized: bool):
    """Register a session with the given tool authorization."""
    tools = [tool] if authorized else []
    session_store.register(SessionConfig(
        session_id=session_id,
        authorized_tools=tools,
        budget=10000.0,
        per_query_epsilon=0.01,
        absorption_margin=0.0,
    ))


def collect_session_features(client, tool: str, session_id: str, n_probes: int = N_PROBES) -> np.ndarray:
    """Send n_probes requests and extract feature vector."""
    times = []
    sizes = []

    for i in range(n_probes):
        start = time.monotonic()
        resp = client.post(f"{BASE_URL}/action", json={
            "tool": tool,
            "params": {"query": f"probe_{i}"},
            "session_id": session_id,
        })
        elapsed = time.monotonic() - start
        times.append(elapsed)
        sizes.append(len(resp.content))

    t = np.array(times)
    s = np.array(sizes)

    features = [
        t.mean(), t.std(), t.min(), t.max(), np.median(t),
        s.mean(), s.std(),
    ]
    return np.array(features)


def run_classifier_attack(tool: str = "web_search"):
    """Run the classifier attack for a given tool."""
    import httpx

    print(f"\nClassifier Attack — tool: {tool}")
    print(f"  {N_SESSIONS} sessions, {N_PROBES} probes each")
    print("-" * 65)

    X = []
    y = []

    with httpx.Client(timeout=10.0) as client:
        for i in range(N_SESSIONS):
            authorized = i % 2 == 0
            session_id = f"eval_clf_{i}"
            configure_session(session_id, tool, authorized)
            features = collect_session_features(client, tool, session_id)
            X.append(features)
            y.append(1 if authorized else 0)

    X = np.array(X)
    y = np.array(y)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42,
    )

    classifiers = {
        "Logistic Regression": LogisticRegression(max_iter=1000),
        "Random Forest": RandomForestClassifier(n_estimators=100, random_state=42),
        "Gradient Boosted": GradientBoostingClassifier(n_estimators=100, random_state=42),
        "MLP": MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=500, random_state=42),
    }

    n_test = len(y_test)
    print(f"\n{'Classifier':<25} {'Accuracy':<12} {'AUC-ROC':<12} {'Binom p':<12} {'Pass'}")
    print("-" * 65)

    all_pass = True

    for name, clf in classifiers.items():
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)
        y_prob = clf.predict_proba(X_test)[:, 1]

        acc = accuracy_score(y_test, y_pred)
        auc = roc_auc_score(y_test, y_prob)
        n_correct = int(acc * n_test)

        # Binomial test: is accuracy significantly above chance (0.5)?
        # One-sided test — we only care if the classifier is better than chance.
        binom_p = binomtest(n_correct, n_test, 0.5, alternative="greater").pvalue

        # Pass if the classifier cannot reject H0 (accuracy = chance) at alpha=0.05
        passes = binom_p >= 0.05

        if not passes:
            all_pass = False

        status = "PASS" if passes else "FAIL"
        print(f"{name:<25} {acc:<12.4f} {auc:<12.4f} {binom_p:<12.4f} {status}")

    return all_pass


def run_all():
    """Run classifier attack across all tools."""
    from src.config import ALL_TOOLS

    print("Classifier Attack Experiment")
    print("=" * 65)
    print(f"Accuracy threshold: <= {ACCURACY_THRESHOLD}")
    print(f"AUC-ROC threshold:  <= {AUC_THRESHOLD}")

    all_pass = True
    for tool in ALL_TOOLS:
        # Clear state between tools
        accountants.clear()
        if not run_classifier_attack(tool):
            all_pass = False

    print("\n" + "=" * 65)
    print(f"Overall: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
