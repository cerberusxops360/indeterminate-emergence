# Known Issues

| ID | Component | Description | Severity | Status |
|----|-----------|-------------|----------|--------|
| KI-001 | channel_shaper / eval | TCP inter-segment timing verified by Experiment 7 sub-test 3. KS p=0.693 (n=50 per path, 48 intra-response deltas each). Mean deltas 134µs (auth) vs 151µs (unauth) — indistinguishable and non-exploitable over any real network (jitter >100µs). Closed. | Low | Closed |
