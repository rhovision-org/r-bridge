# Development harness

Devnet only. Nothing here is a production relayer, and the keys are worth nothing.

## Contents

- `render.py` — fills the deploy template (`contracts/rholo/build/00_bridge.rho`) with
  the network, bridge id, admin/relayer sets and the asset registry.
- `demo.py` — the Phase 1 end-to-end demo. Installs the bridge, signs a deposit with
  2-of-3 dev relayer keys, mints, tests replay/below-threshold/unknown-asset, burns,
  completes the withdrawal, transfers, pauses/unpauses via 2-of-3 admin signatures, and
  checks conservation. Prints PASS/FAIL for each check.
- `mock_relayer.py` — the dev-only HTTP surface from `spec/relayer-interface.md`:
  `/health`, `/v1/chains`, `POST /v1/deposits`, `/v1/deposits/{id}` and
  `/v1/deposits/{id}/attestation`. It watches no chain; it attests what it is told.
- `.devnet/` — generated keys (`demo-keys.json`, mode 600), rendered terms and transient
  files. Gitignored.

## Commands

```
make devnet-up      # local rholo devnet on :40403 (RHOLO_DIR, 8 GB node memory)
make demo           # build the CLI, install the bridge, run the checks
make mock-relayer   # HTTP relayer surface on 127.0.0.1:8099
make devnet-down
```

The first `make demo` generates the deployer/admin/relayer/user keys. Later runs reuse
them, so a re-run installs a fresh bridge at a new URI and repeats the checks.

## What the demo proves

- The bridge contract parses and installs within the deploy budget (15.5 KiB; limit
  56 KiB client / 64 KiB node).
- The canonical attestation digest is reproduced by the Rust signer and the Rholang
  verifier; 2-of-3 works and 1-of-3 is refused.
- Deposit idempotency, asset/amount validation, fee arithmetic, burn records,
  withdrawal completion, holder-signed transfer, pause semantics and conservation.
- The admin surface is 2-of-3 over a nonce-bound canonical payload.

## What it does not prove

- Native-chain custody: no Ethereum/Tron/Agoric vault is deployed yet.
- Finality: the single-validator devnet can report `finalized: false` after
  `ProcessedWithSuccess`; the demo gates on the processed result. Testnet/production
  must require finality.
- Relayer liveness/reorg handling or the production rail; `mock_relayer.py` is a fixed-key
  stand-in, and the rail (standalone bridge node vs rholo plugin/sidecar) is undecided.
