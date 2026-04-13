# Known Issues

| ID | Component | Description | Severity | Status |
|----|-----------|-------------|----------|--------|
| KI-001 | channel_shaper / eval | TCP packet-level timing unverified: 4096-byte responses exceed the 1500-byte MTU, guaranteeing ≥3 TCP segments per response. Inter-segment timing variance between authorized and unauthorized paths is unmeasured. Requires tcpdump with elevated capabilities (`sudo setcap cap_net_raw+eip $(which tcpdump)`) and a dedicated experiment. Until measured, TCP fragmentation timing remains the one unverified software-level distinguishability claim. See `poc/eval/wire_capture.py` sub-test 2. | Low | Open |
