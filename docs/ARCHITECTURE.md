# Architecture

For the full component architecture, see [POC_SPECIFICATION.md](POC_SPECIFICATION.md) Section 3.

The proof of concept consists of five components:

1. **Intent Interface** (proxy.py) -- Single HTTP endpoint, fixed-format responses
2. **Policy Check** (config.py) -- Session-configurable tool authorization
3. **Sealed Executor** (executor.py) -- Normal execution or dummy computation
4. **Channel Shaper** (channel_shaper.py) -- Fixed-size and fixed-timing response normalization
5. **Privacy Accountant** (accountant.py) -- Budget tracking with absorption trigger

All components are specified in POC_SPECIFICATION.md Sections 4.1 through 4.5.
