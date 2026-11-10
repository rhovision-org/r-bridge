# Rholang libraries

Phase 1 writes the shared libraries here:

- `attestation.rho` — canonical message and m-of-n verification.
- `registry.rho` — asset and relayer lookups.
- `conservation.rho` — total/balance arithmetic used by the tests.

Libraries are included into deploy terms at build time; they are not separately
installed.
